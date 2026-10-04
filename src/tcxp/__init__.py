"""tcxp: the Typed ConteXt Protocol reference library.

The address is the state. Everything else (rules, decisions, traces, simulations,
SQL cards) reads or writes addresses.

    >>> import tcxp
    >>> tcxp.__uri__
    '!tcxp:/lib/tcxp?dialect=tcxp-sql/0.1&version=0.1.0'
    >>> a = tcxp.Address.parse("!tcxp:/reason?tax_year=")
    >>> str(a.with_(tax_year=2024))
    '!tcxp:/reason?tax_year=2024'
"""
from .address import MAX_INLINE, Address, AddressError, is_address_text
from .bus import EventBus
from .context import ContextObject, Intent, IntentNotAllowed, Observation, Observatron, Sensor
from .convert import convert
from .facets import DARK, FACETS, LIT, MATCH, NO_MATCH, Equivalences, Spike, dark_count, spikes_in
from .governor import ACT, ASK, HALT, Governor, Rule, Verdict
from .ladder import NOT_STATED, Answer, CodeChecker, Ladder, Question, SimulatedChecker
from .registry import IntegrityError, Registry
from .schema import Field, Schema
from .sql import DIALECT, Database, QueryCard
from .trace import Trace

__version__ = "0.1.0"
__uri__ = str(Address.build("lib/tcxp", {"version": __version__, "dialect": DIALECT}))

__all__ = ["Address", "AddressError", "is_address_text", "MAX_INLINE", "EventBus", "ContextObject", "Intent", "IntentNotAllowed", "Observation",
           "Observatron", "Sensor", "convert", "Spike", "FACETS", "LIT", "DARK", "MATCH", "NO_MATCH", "Equivalences",
           "spikes_in", "dark_count", "Governor", "Rule", "Verdict", "ACT", "ASK", "HALT", "Question", "Answer",
           "Ladder", "CodeChecker", "SimulatedChecker", "NOT_STATED", "Registry", "IntegrityError", "Schema", "Field",
           "Database", "QueryCard", "DIALECT", "Trace", "__version__", "__uri__"]
