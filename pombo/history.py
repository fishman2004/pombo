"""Histórico de envios em CSV: um arquivo por analista por mês.

É também o "estado" do Pombo: o que já saiu é descoberto lendo o histórico.
Se o CSV estiver travado (aberto no Excel), as linhas esperam num arquivo
local de pendentes e são gravadas depois. Nenhuma linha se perde.
"""

import csv
import logging
import threading
import unicodedata
from dataclasses import astuple, dataclass
from datetime import date, datetime
from pathlib import Path

COLUMNS = (
    "data_hora", "analista", "envio", "horario_agendado", "canal",
    "destinatario", "arquivos", "status", "detalhe", "envio_id", "destinatario_id",
)
SUCCESS = {"enviado", "demonstracao"}
log = logging.getLogger(__name__)


class HistoryLocked(Exception):
    """O CSV do histórico não pôde ser lido (provavelmente aberto no Excel)."""


@dataclass(frozen=True)
class Row:
    when: datetime
    analyst: str
    dispatch_name: str
    run: str
    channel: str
    target: str
    files: str
    status: str
    detail: str
    dispatch_id: str
    target_key: str = ""  # vazio em linhas antigas e nas linhas da rodada inteira


def analyst_slug(name: str) -> str:
    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return "-".join(plain.lower().split()) or "analista"


def run_label(scheduled: datetime, manual: bool) -> str:
    if manual:
        return "manual " + scheduled.strftime("%Y-%m-%d %H:%M:%S")
    return scheduled.strftime("%Y-%m-%d %H:%M")


def _to_csv(row: Row) -> list[str]:
    values = list(astuple(row))
    values[0] = row.when.strftime("%Y-%m-%d %H:%M:%S")
    return values


def _from_csv(values: list[str]) -> Row:
    when = datetime.strptime(values[0], "%Y-%m-%d %H:%M:%S")
    if len(values) < 10:
        raise ValueError("linha incompleta")
    # arquivos de versões antigas não têm as colunas do fim
    return Row(when, *(values[1:] + [""] * (len(COLUMNS) - len(values)))[: len(COLUMNS) - 1])


def _read_csv(path: Path) -> list[Row]:
    if not path.exists():
        return []
    rows = []
    with path.open(encoding="utf-8-sig", errors="replace", newline="") as f:
        reader = csv.reader(f)
        next(reader, None)  # cabeçalho
        for number, values in enumerate(reader, start=2):
            if not values:
                continue
            try:
                rows.append(_from_csv(values))
            except (ValueError, TypeError):
                # linha estragada (salva pelo Excel, ou cortada numa queda de energia): ignora e segue
                log.warning("histórico %s: linha %s ignorada", path.name, number)
    return rows


def _append_csv(path: Path, rows: list[Row]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.exists()
    with path.open("a", encoding="utf-8-sig" if new else "utf-8", newline="") as f:
        writer = csv.writer(f)
        if new:
            writer.writerow(COLUMNS)
        writer.writerows(_to_csv(r) for r in rows)


def _write_pending(path: Path, rows: list[Row]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(COLUMNS)
        writer.writerows(_to_csv(r) for r in rows)


def _previous_month(day: date) -> date:
    return date(day.year - 1, 12, 1) if day.month == 1 else date(day.year, day.month - 1, 1)


class History:
    def __init__(self, root: Path, analyst: str, pending_path: Path) -> None:
        self.root = Path(root)
        self.analyst = analyst
        self.pending_path = Path(pending_path)
        self._rows: list[Row] = []
        self._pending: list[Row] = []
        self._lock = threading.Lock()

    def _file_for(self, when: date) -> Path:
        return self.root / analyst_slug(self.analyst) / f"{when:%Y-%m}.csv"

    def load(self, today: date) -> None:
        try:
            # numa unidade de rede fora do ar, exists() só diria "não existe" e o histórico pareceria vazio
            self.root.mkdir(parents=True, exist_ok=True)
            rows = _read_csv(self._file_for(_previous_month(today))) + _read_csv(self._file_for(today))
        except OSError as exc:
            raise HistoryLocked(str(exc)) from exc
        pending = _read_csv(self.pending_path)
        with self._lock:
            self._rows = rows + pending
            self._pending = pending
        self.flush()

    def append(self, row: Row) -> None:
        with self._lock:
            self._rows.append(row)
            self._pending.append(row)
        self.flush()

    def flush(self) -> None:
        with self._lock:
            if not self._pending:
                return
            by_file: dict[Path, list[Row]] = {}
            for r in self._pending:
                by_file.setdefault(self._file_for(r.when.date()), []).append(r)
            still: list[Row] = []
            for path, rows in by_file.items():
                try:
                    _append_csv(path, rows)
                except OSError:
                    still.extend(rows)
            self._pending = still
            if still:
                _write_pending(self.pending_path, still)
            else:
                self.pending_path.unlink(missing_ok=True)

    def rows_for_run(self, dispatch_id: str, run: str) -> list[Row]:
        with self._lock:
            return [r for r in self._rows if r.dispatch_id == dispatch_id and r.run == run]

    def last_success(self, dispatch_id: str) -> datetime | None:
        with self._lock:
            times = [r.when for r in self._rows if r.dispatch_id == dispatch_id and r.status in SUCCESS]
        return max(times, default=None)

    def rows_between(self, start: date, end: date) -> list[Row]:
        with self._lock:
            return [r for r in self._rows if start <= r.when.date() <= end]
