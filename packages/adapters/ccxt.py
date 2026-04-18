"""CCXT / CCXT Pro adapter skeletons for the multiprovider boundary.

Step 1 of the multiprovider migration only needs to prove that the hub
can branch on provider.  The skeletons below do **not** open any network
connections; they exist so the provider registry has concrete factories
for the CCXT and CCXT Pro axes, and so the runtime can raise a clear
``NotImplementedError`` until live crypto connectivity is wired up.

Crypto targets are expected to carry ``instrument_type=spot`` or
``instrument_type=perpetual`` from day 1 so the adapter surface is
structurally ready for USDT-perpetual alongside spot.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from packages.domain.enums import InstrumentType, Provider, Venue


_SUPPORTED_INSTRUMENT_TYPES: tuple[InstrumentType, ...] = (
    InstrumentType.SPOT,
    InstrumentType.PERPETUAL,
)


@dataclass(frozen=True, slots=True)
class CCXTAdapterStub:
    """Descriptor for the CCXT (REST) provider boundary.

    CCXT REST covers reference-data and snapshot flows in the broader
    plan.  Live streaming is handled by :class:`CCXTProAdapterStub`.
    """

    adapter_id: str = "ccxt"
    provider: Provider = Provider.CCXT
    default_venue: Venue = Venue.BINANCE
    implemented: bool = False
    supported_instrument_types: tuple[InstrumentType, ...] = _SUPPORTED_INSTRUMENT_TYPES
    notes: str = "Step 1 skeleton only; REST sync deferred."

    def healthcheck(self) -> bool:
        return False

    def describe(self) -> dict[str, object]:
        return {
            "adapter_id": self.adapter_id,
            "provider": self.provider.value,
            "implemented": self.implemented,
            "supported_instrument_types": tuple(t.value for t in self.supported_instrument_types),
            "notes": self.notes,
        }


@dataclass(frozen=True, slots=True)
class CCXTProAdapterStub:
    """Descriptor for the CCXT Pro (WebSocket) provider boundary.

    Streaming connectivity is deliberately out of scope for step 1.
    Attempting to use the skeleton for live data must fail loudly so
    the runtime never silently degrades into no-op behaviour.
    """

    adapter_id: str = "ccxt_pro"
    provider: Provider = Provider.CCXT_PRO
    default_venue: Venue = Venue.BINANCE
    implemented: bool = False
    supported_instrument_types: tuple[InstrumentType, ...] = _SUPPORTED_INSTRUMENT_TYPES
    notes: str = "Step 1 skeleton only; live WebSocket connectivity deferred."

    def healthcheck(self) -> bool:
        return False

    def describe(self) -> dict[str, object]:
        return {
            "adapter_id": self.adapter_id,
            "provider": self.provider.value,
            "implemented": self.implemented,
            "supported_instrument_types": tuple(t.value for t in self.supported_instrument_types),
            "notes": self.notes,
        }


def build_ccxt_adapter_stub() -> CCXTAdapterStub:
    return CCXTAdapterStub()


def build_ccxt_pro_adapter_stub() -> CCXTProAdapterStub:
    return CCXTProAdapterStub()
