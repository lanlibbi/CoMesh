"""gpu_summary muss alle Karten sehen, nicht nur die erste.

Mit einem gefälschten `pynvml` lässt sich das ohne GPU prüfen: die alte Fassung las ausschließlich
Index 0 und meldete bei zwei Karten eine — die Node war dann im Portal zu klein ausgewiesen.
"""

import importlib.util
import pathlib
import sys
import types

NETINFO = pathlib.Path(__file__).resolve().parent.parent / "node-agent" / "netinfo.py"


class _FakeHandle:
    def __init__(self, name, total):
        self.name = name
        self.total = total


class _FakeMem:
    def __init__(self, total):
        self.total = total


def _fake_pynvml(karten):
    modul = types.SimpleNamespace()
    modul.nvmlInit = lambda: None
    modul.nvmlShutdown = lambda: None
    modul.nvmlDeviceGetCount = lambda: len(karten)
    modul.nvmlDeviceGetHandleByIndex = lambda i: _FakeHandle(*karten[i])
    modul.nvmlDeviceGetName = lambda h: h.name
    modul.nvmlDeviceGetMemoryInfo = lambda h: _FakeMem(h.total)
    return modul


def _lade_netinfo():
    spec = importlib.util.spec_from_file_location("netinfo_multigpu_test", NETINFO)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


def _mit_karten(karten):
    alt = sys.modules.get("pynvml")
    sys.modules["pynvml"] = _fake_pynvml(karten)
    try:
        return _lade_netinfo().gpu_summary()
    finally:
        if alt is None:
            sys.modules.pop("pynvml", None)
        else:
            sys.modules["pynvml"] = alt


def test_zwei_gleiche_karten_werden_summiert():
    ergebnis = _mit_karten([("RTX A2000 12GB", 12884901888)] * 2)
    assert ergebnis["vram_gb"] == 24, ergebnis
    assert ergebnis["count"] == 2, ergebnis
    assert "x2" in ergebnis["name"], ergebnis["name"]


def test_zwei_verschiedene_karten_werden_beide_genannt():
    ergebnis = _mit_karten([("RTX A2000 12GB", 12884901888), ("RTX 3060", 12884901888)])
    assert ergebnis["vram_gb"] == 24, ergebnis
    assert "RTX A2000" in ergebnis["name"] and "RTX 3060" in ergebnis["name"], ergebnis["name"]


def test_eine_karte_bleibt_schlicht():
    ergebnis = _mit_karten([("RTX 4090", 25769803776)])
    assert ergebnis["vram_gb"] == 24, ergebnis
    assert ergebnis["count"] == 1
    assert ergebnis["name"] == "RTX 4090", ergebnis["name"]
