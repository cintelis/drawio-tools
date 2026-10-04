#!/usr/bin/env python3
"""
Bluefield PQC architecture: eight pages with a palette of their own.

The example of drawgen's RAW API: this file keeps its own colours and helpers
(box, zone, cell, text, E) on top of `drawgen.Diagram.add_vertex/add_edge`,
which supply the id guard, the XML and the checks. Hand edits made in draw.io
are overwritten on the next run, so make changes here.

Usage
-----
    uv run python examples/bluefield/build.py            # out/bluefield.drawio + one .drawio.svg per page
    uv run python examples/bluefield/build.py --check    # also fail on checker errors

Adding a page
-------------
1. Create a `Page("p5-<slug>", "5. <Title>")`.
2. Lay out with the helpers on Page: title / zone / box / cell / text / edge.
3. Append the page to PAGES at the bottom of this file.
4. Run with --check, fix anything it reports, then export the SVG to
   assets/05-<slug>.svg and reference it from 05-<slug>.md.

Conventions
-----------
- Canvas is 1200 x 800 per page. Keep content inside x 40..1160, y 16..784.
- Labels are HTML (html=1). Use <br> for line breaks, <b>/<i> for emphasis.
  Do not use "\\n" or "&#10;" - HTML mode ignores them and text collapses.
- Colour semantics are fixed across pages and documented in README.md:
  amber = classical crypto residual, green = post-quantum available now,
  red = untrusted or blocked, blue = DPU enforcement, purple = shared / OOB.
- Every cell id must be unique within a page. Ids "0" and "1" are reserved.

Requires Python 3.8+ and the standard library only.
"""
from __future__ import annotations

import argparse
import html
import os
import sys
from pathlib import Path

from drawgen import Diagram, Document, check_xml
from drawgen.export import render_all

# ---------------------------------------------------------------------------
# Palette (stroke, fill) - keep in step with the README legend
# ---------------------------------------------------------------------------
RED, RED_F = "#B85450", "#FFF4F4"
BLUE, BLUE_F = "#2E6DA4", "#EAF2FB"
GREEN, GREEN_F = "#2D7A46", "#EEF9F1"
GREEN_B = "#D7F0DF"
PURP, PURP_F = "#6B5BA5", "#F5F2FC"
AMB, AMB_F = "#C08A00", "#FDE9C8"
AMB_L = "#FFF8E1"
GREY, GREY_F = "#666666", "#FBFBFD"
STOP, STOP_F = "#CC0000", "#FFE0E0"
WHITE = "#FFFFFF"

CANVAS_W, CANVAS_H = 1200, 800


def esc(s: str) -> str:
    """Escape a label for use inside an XML attribute. HTML tags survive as entities."""
    return html.escape(s, quote=True)


# ---------------------------------------------------------------------------
# Page builder
# ---------------------------------------------------------------------------
class Page(Diagram):
    """One draw.io page with this file's own helpers. Ids are claimed by drawgen."""

    def __init__(self, pid: str, name: str):
        super().__init__(name, CANVAS_W, CANVAS_H, page_id=pid, show_title=False)

    # The original signatures, kept so the page functions below read unchanged.
    def add(self, cid: str, value: str, style: str, x: int, y: int, w: int, h: int) -> None:
        # The legend box and its swatches sit on each other by design; say so to the checker.
        if cid == "legend":
            style += "drawgenRole=legend-box;"
        elif cid.startswith("leg"):
            style += "drawgenRole=legend;"
        self.add_vertex(cid, value, style, x, y, w, h)

    def edge(self, cid: str, src: str, tgt: str, style: str, points=None, value: str = "") -> None:
        self.add_edge(cid, src, tgt, style, points, value)

    # -- helpers ------------------------------------------------------------
    def title(self, t: str, sub: str) -> None:
        self.add("title", t, "text;html=1;align=left;verticalAlign=middle;fontSize=20;fontStyle=1;fontColor=#1A1A1A;", 40, 16, 900, 28)
        self.add("subtitle", sub, "text;html=1;align=left;verticalAlign=middle;fontSize=12;fontColor=#555555;", 40, 42, 1000, 18)

    def zone(self, cid, label, x, y, w, h, stroke, fill, sw=2) -> None:
        """Dashed trust-zone container. Drawn first so components sit on top."""
        st = (f"rounded=1;whiteSpace=wrap;html=1;dashed=1;dashPattern=8 4;fillColor={fill};strokeColor={stroke};"
              f"strokeWidth={sw};verticalAlign=top;align=left;spacingLeft=12;spacingTop=6;fontStyle=1;fontSize=11;fontColor={stroke};drawgenRole=zone;")
        self.add(cid, label, st, x, y, w, h)

    def box(self, cid, label, x, y, w, h, stroke, fill=WHITE, fs=10, bold=False, sw=1,
            align="center", va="middle", dashed=False) -> None:
        """Rounded component box."""
        st = (f"rounded=1;whiteSpace=wrap;html=1;fillColor={fill};strokeColor={stroke};strokeWidth={sw};fontSize={fs};"
              f"align={align};verticalAlign={va};")
        if align == "left":
            st += "spacingLeft=8;spacingRight=8;"
        else:
            st += "spacingLeft=4;spacingRight=4;"
        if va == "top":
            st += "spacingTop=6;"
        if bold:
            st += "fontStyle=1;"
        if dashed:
            st += "dashed=1;dashPattern=4 4;"
        self.add(cid, label, st, x, y, w, h)

    def cell(self, cid, label, x, y, w, h, fill, stroke="#CCCCCC", fs=9, bold=False, color=None) -> None:
        """Square-cornered table cell."""
        st = (f"rounded=0;whiteSpace=wrap;html=1;fillColor={fill};strokeColor={stroke};fontSize={fs};"
              f"align=left;spacingLeft=6;spacingRight=6;verticalAlign=middle;")
        if bold:
            st += "fontStyle=1;"
        if color:
            st += f"fontColor={color};"
        self.add(cid, label, st, x, y, w, h)

    def text(self, cid, label, x, y, w, h, color, fs=9, bold=False, italic=False, align="center", bg=True) -> None:
        """Free text, typically an edge annotation. bg=True paints a white halo."""
        st = f"text;html=1;align={align};verticalAlign=middle;fontSize={fs};fontColor={color};whiteSpace=wrap;"
        fsy = (1 if bold else 0) + (2 if italic else 0)
        if fsy:
            st += f"fontStyle={fsy};"
        if bg:
            st += "labelBackgroundColor=#FFFFFF;"
        self.add(cid, label, st, x, y, w, h)


ORTH = "edgeStyle=orthogonalEdgeStyle;rounded=1;html=1;endArrow=blockThin;endFill=1;"


def E(color: str, sw: int = 2, both: bool = False, dashed: bool = False, extra: str = "") -> str:
    """Edge style builder. `extra` takes exit/entry constraints, e.g. 'exitX=1;exitY=0.5;'."""
    s = ORTH + f"strokeColor={color};strokeWidth={sw};"
    if both:
        s += "startArrow=blockThin;startFill=1;"
    if dashed:
        s += "dashed=1;dashPattern=6 6;"
    return s + extra


# ===========================================================================
# PAGE 1 - TRUST ZONES
# ===========================================================================
def page_trust_zones() -> Page:
    p = Page("p1-trust-zones", "1. Trust Zones")
    p.title("Zero-Trust AI Infrastructure - Trust Zones and Crypto Anchors",
            "BlueField DPU in Zero Trust (Restricted) mode, with a post-quantum control plane. Amber = classical crypto residual.")

    # legend
    p.add("legend", "Legend",
          "rounded=1;whiteSpace=wrap;html=1;fillColor=#FAFAFA;strokeColor=#CCCCCC;verticalAlign=top;align=left;"
          "spacingLeft=10;spacingTop=5;fontStyle=1;fontSize=11;", 920, 12, 240, 54)
    p.box("legPq", "PQ - ML-DSA / ML-KEM", 928, 36, 122, 22, GREEN, GREEN_B, fs=9)
    p.box("legCl", "Classical residual", 1056, 36, 96, 22, AMB, AMB_F, fs=9)

    # zones - the 120px gap between DPU and PQ zones is deliberate; edge labels live there
    p.zone("zoneHost", "TENANT / HOST DOMAIN<br>UNTRUSTED", 40, 80, 280, 470, RED, RED_F)
    p.zone("zoneDpu", "NVIDIA BLUEFIELD DPU<br>ZERO TRUST (RESTRICTED) MODE", 400, 80, 310, 560, BLUE, BLUE_F)
    p.zone("zonePq", "POST-QUANTUM CONTROL PLANE<br>SEPARATE TRUST DOMAIN", 830, 80, 330, 560, GREEN, GREEN_F)
    p.zone("zoneOob", "OUT-OF-BAND MANAGEMENT DOMAIN", 40, 670, 1120, 110, PURP, PURP_F)

    # host column
    HX, HW = 58, 244
    p.box("hTenant", "Tenant workloads<br>VMs / containers / AI jobs", HX, 122, HW, 48, RED, fs=11)
    p.box("hNic", "Host PCIe network function<br>datapath only", HX, 186, HW, 46, RED, fs=11)
    p.box("hOs", "Host OS / hypervisor<br>tenant may hold root", HX, 242, HW, 48, RED, fs=11)
    p.box("gpuTee", "GPU TEE - Hopper / Blackwell, CC mode on<br>encrypted VRAM, separate attestation chain<br>attests via NRAS - also classical today",
          HX, 300, HW, 66, AMB, AMB_L, fs=10, sw=2, dashed=True)
    p.box("hMgmt", "Host-side DPU management<br>rshim / tracer / counters / port owner / FW flash",
          HX, 376, HW, 56, "#999999", "#F5F5F5", fs=10)
    p.text("blockedLbl", "BLOCKED by Restricted mode<br>mlxprivhost -r --disable_rshim --disable_tracer<br>--disable_counter_rd --disable_port_owner",
           HX, 442, HW, 50, STOP, fs=9, bold=True, bg=False)
    p.text("hNote", "Threat actor assumed here:<br>tenant with root on the host", HX, 502, HW, 34, RED, fs=10, italic=True, bg=False)

    # dpu column
    DX, DW = 418, 274
    p.box("dArm", "DPU Arm OS + DOCA runtime<br>unreachable from host", DX, 122, DW, 46, BLUE, fs=11, bold=True)
    p.box("dEnf", "Datapath enforcement<br>OVS-DOCA / DOCA Flow / DPL (P4)<br>micro-segmentation, inline IPsec + TLS offload", DX, 178, DW, 64, BLUE, fs=10)
    p.box("dHbn", "HBN - per-tenant VRF / BGP EVPN<br>OVN VPC System for DPF", DX, 252, DW, 46, BLUE, fs=10)
    p.box("dArgus", "DOCA Argus<br>agentless host memory forensics<br>no host agent, so it survives host compromise", DX, 308, DW, 60, BLUE, fs=10)
    p.box("dTel", "DOCA Telemetry Service<br>Prometheus / OTel / Fluent Bit", DX, 378, DW, 44, BLUE, fs=10)
    p.box("dPqCred", "PQ DEVICE CREDENTIAL - ML-DSA-87<br>held in DPU Arm OS, issued at enrolment<br>this is what gates admission at runtime",
          DX, 432, DW, 62, GREEN, GREEN_B, fs=10, bold=True, sw=2)
    p.box("dRot", "HARDWARE ROOT OF TRUST - RESIDUAL<br>e-FUSE + immutable ROM, DICE L1-L6<br>ECDSA P-384 / SHA2-384, SPDM v1.1<br>not field-upgradable to PQC",
          DX, 504, DW, 76, AMB, AMB_F, fs=10, bold=True, sw=3)
    p.text("dRotNote", "Also applies to ConnectX-7/8/9 and NVLink6 switch ASIC", DX, 586, DW, 20, AMB, fs=9, italic=True, bg=False)

    # pq column
    PX, PW = 848, 294
    p.box("pHsm", "HSM - Entrust nShield 5 or Thales Luna<br>FIPS 140-3 L3 boundary (validation pending)", PX, 122, PW, 46, GREEN, fs=10, bold=True)
    p.box("pVerifier", "IN-HSM ATTESTATION VERIFIER (CodeSafe)<br>SPDM evidence parse + CoRIM reference check<br>runs inside the FIPS boundary, so the verdict<br>is signed by whatever validated it",
          PX, 178, PW, 74, GREEN, GREEN_B, fs=10, sw=2)
    p.box("pCa", "Device Enrolment CA<br>ML-DSA-87 (lattice) + SLH-DSA (hash-based hedge)", PX, 262, PW, 48, GREEN, GREEN_B, fs=10)
    p.box("pVault", "HashiCorp Vault<br>tenant-scoped secrets engines, credential rotation<br>PQ PKI: ML-DSA-87 roots and intermediates", PX, 320, PW, 60, GREEN, GREEN_B, fs=10)
    p.box("pSpire", "SPIFFE / SPIRE<br>workload identity bound to attested node", PX, 390, PW, 44, GREEN, GREEN_B, fs=10)
    p.box("pLog", "Append-only evidence log<br>ML-DSA-87 signed, records the enrolment binding<br>and the pre-CRQC timestamp", PX, 444, PW, 58, GREEN, GREEN_B, fs=10)
    p.box("pInv", "Crypto inventory / crypto-agility control plane<br>ASD deliverable - transition plan by end 2026", PX, 512, PW, 48, GREEN, fs=10)
    p.box("pKek", "Data key wrapping - ML-KEM-1024<br>addresses harvest-now-decrypt-later", PX, 570, PW, 46, GREEN, GREEN_B, fs=10)

    # oob row
    p.box("oKyv", "Kyverno / OPA admission<br>gated on attestation verdict", 58, 706, 250, 58, PURP, fs=10)
    p.box("oBmc", "DPU BMC - Redfish<br>PrivilegeMode = Restricted<br>SPDM attestation endpoint", 400, 706, 250, 58, PURP, fs=10)
    p.box("oDpf", "DPF Operator / DPU cluster control plane<br>declarative CRDs, GitOps", 670, 706, 240, 58, PURP, fs=10)
    p.box("oBfb", "DPF BFB Registry<br>signed bootstream delivery", 930, 706, 212, 58, PURP, fs=10)

    # edges
    p.edge("eData", "hNic", "dEnf", E(BLUE, 2, both=True) + "exitX=1;exitY=0.5;entryX=0;entryY=0.5;")
    p.text("eDataLbl", "tenant datapath<br>via Arm vSwitch", 318, 180, 84, 26, BLUE, fs=9, bold=True, bg=False)

    p.add("eBlockX", "X", "ellipse;whiteSpace=wrap;html=1;fillColor=#CC0000;strokeColor=#CC0000;fontColor=#FFFFFF;fontSize=14;fontStyle=1;", 372, 390, 28, 28)
    p.edge("eBlocked", "hMgmt", "eBlockX", E(STOP, 3, dashed=True, extra="endArrow=none;exitX=1;exitY=0.5;entryX=0;entryY=0.5;"))

    p.edge("eMgmt", "zoneDpu", "oBmc", E(PURP, 2, both=True) + "exitX=0.4;exitY=1;entryX=0.5;entryY=0;")
    p.text("eMgmtLbl", "sole management path - Arm cores or BMC only", 536, 646, 260, 20, PURP, fs=9, bold=True, align="left", bg=False)

    p.edge("eEvidence", "dRot", "pVerifier", E(AMB, 3) + "exitX=1;exitY=0.5;entryX=0;entryY=0.5;", points=[(728, 542), (728, 215)])
    p.text("eEvidenceLbl", "SPDM v1.1 evidence<br>ECDSA P-384<br>classical", 712, 556, 116, 36, AMB, fs=9, bold=True, bg=False)

    p.edge("eCred", "pCa", "dPqCred", E(GREEN, 3) + "exitX=0;exitY=0.5;entryX=1;entryY=0.5;", points=[(812, 286), (812, 463)])
    p.text("eCredLbl", "ML-DSA-87<br>credential<br>issued pre-CRQC<br>post-quantum", 734, 300, 76, 48, GREEN, fs=8, bold=True, bg=False)
    return p


# ===========================================================================
# PAGE 2 - ATTESTATION AND ENROLMENT
# ===========================================================================
def page_attestation() -> Page:
    p = Page("p2-attestation", "2. Attestation and Enrolment")
    p.title("Attestation and Enrolment - Trust Transfer from Classical to Post-Quantum Anchor",
            "The classical ECDSA P-384 chain is consulted exactly once, at enrolment, while it is still sound. Everything after that is post-quantum.")

    p.zone("phA", "PHASE A - ENROLMENT<br>one-time per device, performed while ECDSA P-384 is still sound (pre-CRQC)", 40, 80, 1120, 300, GREY, GREY_F)
    AY, AH = 124, 104
    p.box("a1", "<b>1. Secure boot</b><br><br>ROM root of trust verifies the boot chain. DICE L5/L6 generated in volatile memory; L6 signs measurements.",
          62, AY, 190, AH, AMB, AMB_F, fs=10, sw=2, align="left", va="top")
    p.box("a2", "<b>2. Evidence collection</b><br><br>SPDM GET_CERTIFICATE slot 0 via DPU BMC Redfish. Returns the L1-L6 chain plus TCG_DICE_FWID-0 and -1.",
          282, AY, 190, AH, AMB, AMB_F, fs=10, sw=2, align="left", va="top")
    p.box("a3", "<b>3. Validation inside the HSM</b><br><br>In-boundary verifier (CodeSafe): validate the cert chain, compare SHA2-384 FWIDs against the CoRIM reference manifest.",
          502, AY, 210, AH, GREEN, GREEN_B, fs=10, sw=3, align="left", va="top")
    p.box("a4", "<b>4. Issue PQ credential</b><br><br>Enrolment CA issues an ML-DSA-87 certificate bound to the device identity and the measured FWID values.",
          742, AY, 190, AH, GREEN, GREEN_B, fs=10, sw=3, align="left", va="top")
    p.box("a5", "<b>5. Record the binding</b><br><br>Append-only log, ML-DSA-87 signed: device ID, FWIDs, issued cert, enrolment timestamp (the pre-CRQC proof).",
          962, AY, 180, AH, GREEN, GREEN_B, fs=10, sw=3, align="left", va="top")
    p.edge("ea12", "a1", "a2", E("#333333", 2))
    p.edge("ea23", "a2", "a3", E("#333333", 2))
    p.edge("ea34", "a3", "a4", E(GREEN, 3))
    p.edge("ea45", "a4", "a5", E(GREEN, 3))
    p.text("ea34l", "PASS", 705, 158, 44, 16, GREEN, fs=9, bold=True)
    p.box("aQ", "<b>QUARANTINE - do not enrol</b><br>raise incident, verify physical provenance", 502, 262, 210, 50, STOP, STOP_F, fs=10, sw=2)
    p.edge("eaQ", "a3", "aQ", E(STOP, 2))
    p.text("eaQl", "FWID / CoRIM mismatch", 616, 236, 130, 16, STOP, fs=9, bold=True, align="left")
    p.box("noteCl", "<i>Classical crypto is trusted ONLY in steps 1-3, and only at enrolment time.<br>ECDSA P-384 / SHA2-384 / SPDM v1.1 - fixed in silicon, not upgradable.</i>",
          62, 326, 410, 44, AMB, AMB_L, fs=10, sw=2)
    p.box("noteQ", "<i>After step 4 the classical chain is never consulted again. Platform admission<br>depends solely on the ML-DSA-87 credential. Trust has been transferred.</i>",
          742, 326, 400, 44, GREEN, GREEN_F, fs=10, sw=2)

    p.zone("phB", "PHASE B - RUNTIME<br>repeated continuously, post-quantum only", 40, 400, 1120, 180, GREEN, GREEN_F)
    BY, BH = 444, 66
    p.box("b1", "<b>6. Device presents</b><br>ML-DSA-87 credential<br>(held in DPU Arm OS)", 62, BY, 196, BH, GREEN, fs=10, sw=2)
    p.box("b2", "<b>7. SPIFFE / SPIRE</b><br>node attestation, issues<br>SVIDs to workloads", 288, BY, 196, BH, GREEN, fs=10, sw=2)
    p.box("b3", "<b>8. Vault auth</b><br>tenant-scoped role,<br>dynamic secrets, rotation", 514, BY, 196, BH, GREEN, fs=10, sw=2)
    p.box("b4", "<b>9. Kyverno / OPA gate</b><br>admission requires a<br>current attestation verdict", 740, BY, 196, BH, GREEN, fs=10, sw=2)
    p.box("b5", "<b>10. Tenant workload</b><br>scheduled onto the<br>attested node only", 966, BY, 176, BH, GREEN, fs=10, sw=2)
    for a, b in [("b1", "b2"), ("b2", "b3"), ("b3", "b4"), ("b4", "b5")]:
        p.edge(f"e{a}{b}", a, b, E(GREEN, 2))
    p.text("bNote", "Continuous validation: DOCA Argus memory forensics and DOCA Telemetry feed runtime posture. Isolation is re-validated before every tenant onboarding, not only at build time.",
           62, 524, 1080, 40, GREEN, fs=10, italic=True, bg=False)

    p.box("why", "<b>WHY THIS HOLDS</b><br><br>Attestation signatures are verified and then discarded, so there is no harvest-now-decrypt-later exposure on the classical chain. A CRQC that can forge ECDSA P-384 after 2030 gains nothing here, because platform admission depends on an ML-DSA-87 credential that was issued before the CRQC existed and cannot be re-minted without re-enrolment.",
          40, 600, 550, 112, GREEN, GREEN_F, fs=10, sw=2, align="left", va="top")
    p.box("ctrl", "<b>THE CONTROL POINT - RE-ENROLMENT</b><br><br>Any device enrolled after a CRQC exists inherits a forgeable anchor, so re-enrolment is the highest-governance operation in the platform. Requires change control, physical provenance evidence, dual authorisation, and an entry in the signed evidence log. Security is asserted as at the enrolment date - state this explicitly in the design.",
          610, 600, 550, 112, RED, RED_F, fs=10, sw=2, align="left", va="top")
    return p


# ===========================================================================
# PAGE 3 - TENANT ISOLATION AND ENFORCEMENT
# ===========================================================================
def page_isolation() -> Page:
    p = Page("p3-isolation", "3. Tenant Isolation and Enforcement")
    p.title("Zero-Trust Tenant Isolation and Enforcement Plane",
            "Every enforcement point sits on the DPU Arm cores, outside the host trust domain. Default deny at each layer. Validation precedes onboarding.")

    p.zone("tA", "TENANT A - untrusted", 40, 82, 290, 180, RED, RED_F)
    p.box("tAw", "AI workloads / containers<br>tenant holds root on host", 58, 112, 254, 44, RED, fs=10)
    p.box("tAg", "GPU slice - CC mode on<br>encrypted VRAM, own attestation", 58, 164, 254, 44, AMB, AMB_L, fs=10)
    p.box("tAv", "Vault namespace A - scoped secrets only", 58, 216, 254, 34, GREEN, GREEN_B, fs=9)
    p.zone("tB", "TENANT B - untrusted", 350, 82, 290, 180, RED, RED_F)
    p.box("tBw", "AI workloads / containers<br>tenant holds root on host", 368, 112, 254, 44, RED, fs=10)
    p.box("tBg", "GPU slice - CC mode on<br>encrypted VRAM, own attestation", 368, 164, 254, 44, AMB, AMB_L, fs=10)
    p.box("tBv", "Vault namespace B - scoped secrets only", 368, 216, 254, 34, GREEN, GREEN_B, fs=9)
    p.add("xTen", "NO PATH", "ellipse;whiteSpace=wrap;html=1;fillColor=#CC0000;strokeColor=#CC0000;fontColor=#FFFFFF;fontSize=9;fontStyle=1;", 308, 152, 64, 30)

    p.zone("sh", "SHARED INFRASTRUCTURE - what is being isolated", 660, 82, 500, 180, PURP, PURP_F)
    p.box("shF", "Spectrum-X Ethernet / NVLink fabric<br>ConnectX-8 / -9, NVLink6 switch - classical device identity", 678, 112, 464, 44, PURP, fs=10)
    p.box("shS", "Shared NVMe-oF storage<br>SNAP / NVMF target offload, per-tenant namespaces", 678, 164, 464, 44, PURP, fs=10)
    p.box("shG", "Shared GPU pool and platform services - Kubernetes / OpenShift control plane", 678, 216, 464, 34, PURP, fs=10)

    p.zone("ep", "ENFORCEMENT PLANE - BlueField DPU Arm cores, Zero Trust (Restricted) mode, one per host", 40, 300, 1120, 212, BLUE, BLUE_F, sw=3)
    EY, EH = 340, 154
    p.box("e1", "<b>E1 - IDENTITY</b><br><br>SPIFFE SVID derived from the attested node credential.<br><br>Vault auth bound to device identity, NOT to a host service account.<br><br>Trust anchor sits outside the tenant blast radius.",
          58, EY, 205, EH, BLUE, fs=9, sw=2, align="left", va="top")
    p.box("e2", "<b>E2 - MICRO-SEGMENTATION</b><br><br>OVS-DOCA / DOCA Flow offloaded flow rules.<br><br>DPL (P4) pipelines for custom datapath policy.<br><br><b>DEFAULT DENY</b> - east-west blocked unless explicitly permitted.",
          278, EY, 205, EH, BLUE, fs=9, sw=2, align="left", va="top")
    p.box("e3", "<b>E3 - L3 / VPC ISOLATION</b><br><br>HBN: per-tenant VRF, BGP with EVPN extension.<br><br>OVN VPC System for DPF: VPC abstraction and security groups.<br><br>Tenant routing tables are disjoint by construction.",
          498, EY, 205, EH, BLUE, fs=9, sw=2, align="left", va="top")
    p.box("e4", "<b>E4 - CRYPTO BOUNDARY</b><br><br>Inline IPsec ESP offload, AES-256-GCM (PQ-neutral).<br><br>IKEv2 key exchange with ML-KEM-1024 - software on Arm cores, the PKA has no PQC.<br><br>Size SA rekey rate: PQ handshakes are not offloaded.",
          718, EY, 205, EH, GREEN, GREEN_B, fs=9, sw=2, align="left", va="top")
    p.box("e5", "<b>E5 - OBSERVATION</b><br><br>DOCA Argus: agentless host memory forensics from the Arm cores.<br><br>No host agent to disable, so detection survives host compromise.<br><br>DOCA Telemetry to SIEM, scoped per tenant.",
          938, EY, 205, EH, BLUE, fs=9, sw=2, align="left", va="top")

    p.edge("eA", "tA", "ep", E(RED, 2) + "exitX=0.5;exitY=1;entryX=0.13;entryY=0;")
    p.edge("eB", "tB", "ep", E(RED, 2) + "exitX=0.5;exitY=1;entryX=0.406;entryY=0;")
    p.edge("eSh", "ep", "sh", E(PURP, 2, both=True) + "exitX=0.888;exitY=0;entryX=0.75;entryY=1;")
    p.text("eShL", "only permitted, tenant-tagged<br>traffic reaches shared infra", 866, 266, 160, 30, PURP, fs=9, bold=True, align="right", bg=False)

    p.zone("vb", "PRE-ONBOARDING ISOLATION VALIDATION - no tenant is onboarded until every test passes and the evidence pack is signed", 40, 530, 1120, 226, GREY, GREY_F)
    VY, VH = 574, 110
    p.box("v1", "<b>V1 - Cross-tenant reachability</b><br><br>Active probe from A to B across every path: L2, L3, storage, control plane. Must fail closed.", 58, VY, 205, VH, GREY, fs=9, sw=2, align="left", va="top")
    p.box("v2", "<b>V2 - Policy conformance</b><br><br>Rendered DPF / HBN / OVN state diffed against declared intent. Kyverno and OPA dry-run against the manifest.", 278, VY, 205, VH, GREY, fs=9, sw=2, align="left", va="top")
    p.box("v3", "<b>V3 - Secret scope</b><br><br>Tenant A credential proven unable to read any B path. Rotation and revocation exercised, not assumed.", 498, VY, 205, VH, GREY, fs=9, sw=2, align="left", va="top")
    p.box("v4", "<b>V4 - Crypto conformance</b><br><br>Algorithm inventory matched to the ASD set: ML-KEM-1024 and ML-DSA-87. Any classical or transitional use recorded.", 718, VY, 205, VH, AMB, AMB_L, fs=9, sw=2, align="left", va="top")
    p.box("v5", "<b>ONBOARDING GATE</b><br><br>Evidence pack signed ML-DSA-87 and logged.<br><br><b>No pass, no tenant.</b>", 938, VY, 205, VH, GREEN, GREEN_B, fs=9, sw=3, align="left", va="top")
    p.edge("ev12", "v1", "v2", E(GREY, 2))
    p.edge("ev23", "v2", "v3", E(GREY, 2))
    p.edge("ev34", "v3", "v4", E(GREY, 2))
    p.edge("ev45", "v4", "v5", E(GREEN, 3))
    p.text("vNote", "All of the above is expressed as policy-as-code and driven through GitOps against DPF CRDs, so the validation is repeatable per tenant, per release, and produces the audit artefact rather than a one-off report.",
           58, 700, 1085, 40, "#444444", fs=10, italic=True, bg=False)
    return p


# ===========================================================================
# PAGE 4 - CRYPTO POSTURE
# ===========================================================================
def page_crypto_posture() -> Page:
    p = Page("p4-crypto", "4. Crypto Posture and ASD Alignment")
    p.title("Cryptographic Posture Map and ASD 2030 Alignment",
            "One row per cryptographic use in the platform. This is the artefact that answers the ASD end-2026 transition-plan requirement.")
    p.zone("tl", "ASD POST-QUANTUM TRANSITION TIMELINE", 40, 70, 1120, 144, GREY, GREY_F)
    p.box("m1", "<b>END 2026</b><br>Refined transition plan in place - requires a cryptographic inventory", 58, 96, 345, 44, AMB, AMB_L, fs=9, sw=2)
    p.box("m2", "<b>END 2028</b><br>Migration under way for critical systems and long-lived sensitive data", 413, 96, 345, 44, AMB, AMB_F, fs=9, sw=2)
    p.box("m3", "<b>END 2030</b><br>RSA, DH, ECDH and ECDSA retired - no traditional asymmetric crypto", 768, 96, 374, 44, STOP, STOP_F, fs=9, sw=2)
    p.box("ap", "ASD approved sets: <b>ML-KEM-1024</b> preferred (ML-KEM-768 transitional only) - <b>ML-DSA-87</b> preferred (ML-DSA-65 permitted but not beyond 2030). Hybrid schemes are not recommended, though not prohibited as an interim step.",
          58, 146, 1084, 24, GREEN, GREEN_F, fs=9, sw=1)
    p.box("trap", "<b>THE TRAP:</b> the global default hybrid is X25519 + ML-KEM-768. Both halves are unapproved after 2030, so inheriting vendor and hyperscaler defaults buys a second migration inside the same decade.<br>Specify ML-KEM-1024 and ML-DSA-87 wherever you control the configuration; record a tracked residual wherever you do not.",
          58, 174, 1084, 34, STOP, STOP_F, fs=9, sw=2)

    COLS = [(40, 270), (310, 230), (540, 230), (770, 150), (920, 240)]
    HDR = ["CRYPTOGRAPHIC USE", "TODAY", "ASD-ALIGNED TARGET", "STATUS", "ARCHITECTURAL ACTION"]
    TY = 224
    for i, (h, (cx, cw)) in enumerate(zip(HDR, COLS)):
        p.cell(f"h{i+1}", h, cx, TY, cw, 30, "#333333", "#333333", fs=9, bold=True, color=WHITE)

    # status swatches: (fill, stroke, fontColor)
    BLK = (STOP_F, STOP, STOP)
    UNK = ("#EEEEEE", "#999999", "#666666")
    AV = (GREEN_B, GREEN, GREEN)
    PART = (AMB_F, AMB, AMB)

    ROWS = [
        (AMB_L, "<b>Device identity and attestation</b><br>BlueField-3, ConnectX-7/8/9, NVLink6", "ECDSA P-384, SHA2-384<br>SPDM v1.1", "ML-DSA-87 carried over SPDM 1.4", BLK, "<b>BLOCKED</b><br>fixed in silicon", "Named residual + enrolment trust transfer. NDA question to NVIDIA on BF-4 and SPDM 1.4."),
        (AMB_L, "<b>Secure boot and firmware signing</b><br>BlueField boot chain", "Not published by NVIDIA<br>e-FUSE key hash, off-chip pubkey", "LMS or XMSS - CNSA 2.0 restricts these to firmware signing", UNK, "<b>UNKNOWN</b><br>not disclosed", "Separate chain from attestation - could already be quantum-safe. Ask NVIDIA directly, do not assume."),
        (AMB_L, "<b>GPU confidential computing attestation</b><br>Hopper / Blackwell via NRAS", "Classical signing<br>separate chain from the DPU", "ML-DSA-87", BLK, "<b>BLOCKED</b><br>vendor dependency", "Fold into the composite verdict. Same enrolment-window treatment as the DPU chain."),
        (GREEN_F, "<b>Device enrolment credential</b><br>the PQ anchor", "Does not exist yet<br>new control", "ML-DSA-87 primary, SLH-DSA as non-lattice hedge", AV, "<b>AVAILABLE NOW</b>", "HSM-backed CA. nShield 5 fw 13.8.0 has all three CAVP-validated; Luna 7.9 has two."),
        (GREEN_F, "<b>Platform PKI and workload identity</b><br>Vault, SPIFFE, service mesh", "RSA / ECDSA / Ed25519", "ML-DSA-87 roots and intermediates", AV, "<b>AVAILABLE NOW</b><br>verify release", "Vault PKI ML-DSA-65/87 via circl. Confirm the shipped release before committing in design."),
        (GREEN_F, "<b>Tenant traffic key establishment</b><br>IKEv2 for IPsec tunnels", "ECDH P-384<br>accelerated by the DPU PKA", "ML-KEM-1024", AV, "<b>AVAILABLE NOW</b><br>perf impact", "PKA has no PQC, so this runs in software on Arm. Size SA rekey and session-establishment rate."),
        ("#F5F5F5", "<b>Tenant traffic bulk encryption</b><br>IPsec ESP, inline TLS offload", "AES-256-GCM<br>hardware offloaded", "AES-256-GCM - unchanged", UNK, "<b>NOT AFFECTED</b>", "Symmetric crypto is quantum-resistant at 256-bit. Full line-rate offload retained. No action."),
        (STOP_F, "<b>Data-at-rest key wrapping</b><br>long-lived tenant data and models", "RSA / ECDH key wrapping", "ML-KEM-1024 in the HSM", AV, "<b>DO THIS FIRST</b><br>HNDL exposure", "The only genuine harvest-now-decrypt-later exposure in the platform. Highest priority, lowest difficulty."),
        (AMB_L, "<b>Kubernetes / OpenShift control plane TLS</b><br>and service mesh mTLS", "X25519 + ML-KEM-768<br>Go 1.24+ default", "ML-KEM-1024, non-hybrid", PART, "<b>PARTIAL</b><br>this is the trap", "Compliant-looking today, non-compliant in 2030. Override the default; record where you cannot."),
        (GREEN_F, "<b>Evidence log and audit signing</b><br>enrolment and isolation evidence packs", "Does not exist yet<br>new control", "ML-DSA-87, HSM-held key", AV, "<b>AVAILABLE NOW</b>", "Signatures must outlive the devices they attest, so this is a long-lived signing use. PQ from day one."),
        (AMB_L, "<b>Image and model artefact signing</b><br>Sigstore cosign, admission verification (06, 07)", "ECDSA P-256<br>HSM-held key via PKCS#11", "ML-DSA-87 when cosign / Fulcio / Rekor support ships", PART, "<b>PARTIAL</b><br>vendor dependency", "Signatures re-verified at every admission, so no HNDL exposure. HSM key rotatable when tooling lands."),
    ]
    RY, RH = TY + 30, 42
    for r, (c1fill, c1, c2, c3, st, c4, c5) in enumerate(ROWS, start=1):
        y = RY + (r - 1) * RH
        p.cell(f"r{r}c1", c1, COLS[0][0], y, COLS[0][1], RH, c1fill)
        p.cell(f"r{r}c2", c2, COLS[1][0], y, COLS[1][1], RH, WHITE)
        p.cell(f"r{r}c3", c3, COLS[2][0], y, COLS[2][1], RH, WHITE)
        p.cell(f"r{r}c4", c4, COLS[3][0], y, COLS[3][1], RH, st[0], st[1], color=st[2])
        p.cell(f"r{r}c5", c5, COLS[4][0], y, COLS[4][1], RH, WHITE)
    FY = RY + len(ROWS) * RH + 12
    p.box("foot", "<b>HONEST SUMMARY FOR THE CLIENT:</b> seven of eleven cryptographic uses can be made ASD-2030 aligned today. Three depend on vendors: NVIDIA device and GPU identity is ECDSA P-384 on SPDM v1.1 with no published migration path, and Sigstore is ECDSA P-256 with PQ work unshipped. One is unknown pending NVIDIA. The device identity gap is carried as a named, time-bounded residual, mitigated by pre-CRQC enrolment onto a post-quantum credential, and closed by hardware refresh. Do not write \"post-quantum throughout\" on a slide - it is not true at the device trust layer, and their engineers will know.",
          40, FY, 1120, 62, "#333333", GREY_F, fs=10, sw=2, align="left")
    return p


# ===========================================================================
# PAGE 5 - PLATFORM HARDENING AND IDENTITY
# ===========================================================================
def page_platform_identity() -> Page:
    p = Page("p5-platform", "5. Platform Hardening and Identity")
    p.title("Platform Hardening and Identity - Two Identity Planes, One Admission Gate",
            "Human identity is federated from the client IdP; workload identity is derived from the attested node. Both must pass admission. In-cluster controls sit above the DPU plane.")

    # identity planes
    p.zone("zHuman", "HUMAN IDENTITY PLANE<br>federated, never hosted", 40, 80, 545, 205, PURP, PURP_F)
    p.box("idp", "Client IdP<br>Entra ID / Okta / AD<br>authoritative users and groups, MFA", 58, 118, 160, 60, PURP, fs=10)
    p.box("kc", "Keycloak or Entra ID<br>federation broker<br>SAML / OIDC in, OIDC out", 238, 118, 160, 60, PURP, fs=10, bold=True)
    p.box("oauth", "OpenShift OAuth /<br>API server OIDC<br>group claims mapped to RBAC", 418, 118, 149, 60, PURP, fs=10)
    p.edge("e_idp_kc", "idp", "kc", E(PURP, 2)); p.edge("e_kc_oauth", "kc", "oauth", E(PURP, 2))
    p.box("humanRules", "<b>Rules</b> - groups only in RBAC, never users (P7) - tenant group names are a contract: tenant-&lt;id&gt;-admin / developer / viewer - tokens 15 min or less, no long-lived kubeconfig - MFA enforced upstream, amr claim checked above viewer - break-glass separate, hardware-key protected, alerts on use",
          58, 190, 509, 78, PURP, WHITE, fs=9, align="left", va="top")

    p.zone("zWork", "WORKLOAD IDENTITY PLANE<br>anchored outside the host", 615, 80, 545, 205, GREEN, GREEN_F)
    p.box("node", "Attested node<br>ML-DSA-87 device credential<br>from enrolment (02)", 633, 118, 160, 60, GREEN, GREEN_B, fs=10, bold=True)
    p.box("spire", "SPIRE server + agent<br>node attestation<br>issues SVIDs to pods", 813, 118, 160, 60, GREEN, GREEN_B, fs=10)
    p.box("vault", "Vault auth on SVID<br>tenant-scoped role<br>dynamic secrets, rotation", 993, 118, 149, 60, GREEN, GREEN_B, fs=10)
    p.edge("e_node_spire", "node", "spire", E(GREEN, 2)); p.edge("e_spire_vault", "spire", "vault", E(GREEN, 2))
    p.box("workRules", "<b>Rules</b> - no long-lived Kubernetes Secrets holding credentials - automountServiceAccountToken=false by default (P9) - Vault auth is bound to device identity, NOT to a host service account - the trust anchor sits outside the tenant blast radius, which is what connects 02 to access control",
          633, 190, 509, 78, GREEN, WHITE, fs=9, align="left", va="top")

    # admission gate
    p.zone("zAdm", "ADMISSION GATE - Kyverno / OPA Gatekeeper, policy-as-code under GitOps", 40, 312, 1120, 150, BLUE, BLUE_F, sw=3)
    p.box("kyv", "<b>Kyverno + OPA</b><br><br>Every policy links to the control it satisfies. Exceptions are namespaced, time-bounded, justified, and expire in CI.",
          58, 350, 222, 96, BLUE, WHITE, fs=9, sw=2, align="left", va="top")
    chips = [
        ("P1", "PSS restricted<br>on tenant namespaces"), ("P2", "images signed<br>and scanned"), ("P3", "approved registry<br>only"),
        ("P4", "digest pinned,<br>no :latest"), ("P5", "schedule only to<br>attested GPU nodes"),
        ("P6", "immutable tenant<br>label required"), ("P7", "group RBAC only,<br>no user bindings"), ("P8", "requests and<br>limits required"),
        ("P9", "no auto-mounted<br>SA token"), ("P10", "seccomp default,<br>read-only rootfs"),
    ]
    for i, (pid, txt) in enumerate(chips):
        cx = 300 + (i % 5) * 170; cy = 350 + (i // 5) * 50
        p.box(f"chip{pid}", f"<b>{pid}</b> {txt}", cx, cy, 160, 42, BLUE, WHITE, fs=9)
    p.edge("e_h_adm", "zHuman", "zAdm", E(PURP, 3) + "exitX=0.5;exitY=1;entryX=0.25;entryY=0;")
    p.edge("e_w_adm", "zWork", "zAdm", E(GREEN, 3) + "exitX=0.5;exitY=1;entryX=0.75;entryY=0;")
    p.text("admLbl", "an authorised human cannot schedule onto an unattested node; an attested node cannot run an unauthorised human's workload",
           300, 288, 600, 20, BLUE, fs=9, italic=True, bg=False)

    # tenant namespaces and hardening
    p.zone("zNs", "TENANT NAMESPACES AND PLATFORM HARDENING - inside the host trust domain", 40, 490, 1120, 190, GREY, GREY_F)
    p.box("nsA", "<b>Tenant A namespaces</b><br>label tenant=a (immutable)<br>ResourceQuota + LimitRange, GPU quota<br>PSS restricted, Cilium default deny", 58, 528, 250, 72, RED, RED_F, fs=9)
    p.box("nsB", "<b>Tenant B namespaces</b><br>label tenant=b (immutable)<br>ResourceQuota + LimitRange, GPU quota<br>PSS restricted, Cilium default deny", 328, 528, 250, 72, RED, RED_F, fs=9)
    p.box("cil", "<b>Cilium</b> - in-cluster network policy<br>clusterwide default deny, FQDN egress allow-lists per tenant<br>optional mTLS on SVIDs, Hubble flows to SIEM", 598, 528, 270, 72, BLUE, WHITE, fs=9)
    p.box("cis", "<b>Hardening baseline</b><br>CIS via Compliance Operator / kube-bench<br>API audit, etcd encryption via HSM KMS<br>operator stack pinned to certified versions", 888, 528, 254, 72, BLUE, WHITE, fs=9)
    p.text("nsNote", "Namespaces are a soft boundary alone. Cilium, Kyverno webhooks and the kubelet can all be affected by a tenant with root on the host. That is why the plane below exists.",
           58, 612, 1085, 40, "#444444", fs=10, italic=True, bg=False)

    p.zone("zDpu", "DPU ENFORCEMENT PLANE (03) - outside the host trust domain, survives host compromise, Argus detects the attempt", 40, 706, 1120, 60, BLUE, BLUE_F, sw=3)
    p.edge("e_ns_dpu", "zNs", "zDpu", E(BLUE, 2) + "exitX=0.5;exitY=1;entryX=0.5;entryY=0;")
    return p


# ===========================================================================
# PAGE 6 - SUPPLY CHAIN AND RUNTIME SECURITY
# ===========================================================================
def page_supply_chain() -> Page:
    p = Page("p6-supply", "6. Supply Chain and Runtime Security")
    p.title("Supply Chain and Runtime Security - One Trust Root, Two Detection Layers",
            "Nothing runs that we did not build, scan and sign. Anything behaving unexpectedly is detected by two layers with different failure modes and reaches the client SOC.")

    p.zone("zPipe", "BUILD AND SIGN PIPELINE", 40, 80, 1120, 210, GREY, GREY_F)
    stages = [
        ("s1", "<b>Source</b><br><br>Git, protected branches, signed commits<br><br><i>gate: two-person review on policy/ and platform/</i>", GREY, WHITE),
        ("s2", "<b>Build</b><br><br>Reproducible; base images from approved registry only<br><br><i>gate: fail on unpinned or unapproved base</i>", GREY, WHITE),
        ("s3", "<b>SBOM</b><br><br>Syft, SPDX + CycloneDX, attached as in-toto attestation<br><br><i>gate: no SBOM = build fails</i>", GREY, WHITE),
        ("s4", "<b>Scan</b><br><br>Trivy / Grype on image AND SBOM; NVIDIA CVE feed for NGC images<br><br><i>gate: critical/high with fix fails</i>", AMB, AMB_L),
        ("s5", "<b>Sign</b><br><br>cosign with HSM-held key via PKCS#11, not keyless; private Rekor if required<br><br><i>gate: unsigned cannot push to prod</i>", GREEN, GREEN_B),
        ("s6", "<b>Registry</b><br><br>Harbor / Quay, private, per-tenant projects; quarantine to prod only after gates<br><br><i>pull from anywhere else blocked</i>", GREY, WHITE),
    ]
    for i, (cid, txt, stroke, fill) in enumerate(stages):
        p.box(cid, txt, 58 + i * 185, 118, 170, 104, stroke, fill, fs=9, sw=2, align="left", va="top")
        if i: p.edge(f"e_{stages[i-1][0]}_{cid}", stages[i-1][0], cid, E("#333333", 2))
    p.box("pipeNote", "NVIDIA images from NGC are consumed as evidence, then re-scanned and re-signed under <b>our</b> key: one trust root at admission. Scan attestations expire after 7 days - an image clean in March is not known clean in September.",
          58, 232, 980, 44, GREY, WHITE, fs=9, sw=1)

    p.zone("zAdm", "ADMISSION", 40, 310, 1120, 108, BLUE, BLUE_F, sw=3)
    p.box("adm", "<b>Kyverno verifyImages / Sigstore policy-controller</b>&nbsp;&nbsp;&nbsp; signature valid &#10003; &nbsp; SBOM attestation present &#10003; &nbsp; scan attestation under 7 days &#10003; &nbsp; digest pinned &#10003; &nbsp; approved registry &#10003;",
          58, 346, 720, 56, BLUE, WHITE, fs=9, sw=2)
    p.box("kpi", "<b>KPI</b> - zero unsigned or unscanned images admitted to production; runtime detection live before the first tenant workload", 798, 346, 344, 56, GREEN, GREEN_B, fs=9, sw=2)
    p.edge("e_s6_adm", "s6", "adm", E(BLUE, 3) + "exitX=0.5;exitY=1;entryX=0.95;entryY=0;", points=[(1068, 298), (742, 298)])

    p.zone("zRun", "RUNTIME DETECTION - two layers, different failure modes", 40, 438, 700, 195, BLUE, BLUE_F)
    p.box("falco", "<b>Falco</b> (eBPF) - in-cluster<br><br>Syscalls, container lifecycle, Kubernetes audit. Platform rules: shell in GPU container, unexpected /dev/nvidia* access, model file read by non-serving process, egress outside Cilium policy, kubectl exec by non-tenant identity.<br><br><b>Inside the host trust domain - can be silenced.</b>",
          58, 476, 320, 118, BLUE, WHITE, fs=9, sw=2, align="left", va="top")
    p.box("argus", "<b>DOCA Argus</b> - DPU-side<br><br>Host memory, process and module integrity observed from the Arm cores. No host agent to disable.<br><br><b>Outside the host trust domain - survives host compromise.</b>",
          400, 476, 320, 118, BLUE, GREEN_B, fs=9, sw=2, align="left", va="top")
    p.text("corr", "Falco going quiet on a node while Argus still shows activity is itself an alert.", 58, 600, 662, 24, BLUE, fs=10, bold=True, bg=False)
    p.edge("e_adm_run", "zAdm", "zRun", E(BLUE, 2) + "exitX=0.3125;exitY=1;entryX=0.5;entryY=0;")

    p.zone("zSiem", "CLIENT SIEM / SOC - they own response", 760, 438, 400, 195, PURP, PURP_F)
    p.box("siem", "<b>Client SIEM</b> - Splunk / Sentinel / Elastic<br>ECS or OCSF schema agreed at onboarding<br>every event carries tenant=&lt;id&gt;", 778, 476, 364, 60, PURP, WHITE, fs=9, sw=2)
    p.box("src", "Sources: Falco, Argus + DTS, Kubernetes audit, Hubble flows, Kyverno policy reports, ArgoCD sync status", 778, 544, 364, 44, PURP, WHITE, fs=9)
    p.text("socNote", "Detection content and a tabletop exercise are delivered at handover.", 778, 596, 364, 28, PURP, fs=9, italic=True, bg=False)
    p.edge("e_run_siem", "zRun", "zSiem", E(PURP, 3) + "exitX=1;exitY=0.4;entryX=0;entryY=0.4;")

    p.zone("zGit", "GITOPS - zero drift", 40, 652, 1120, 112, GREEN, GREEN_F)
    p.box("argo", "<b>ArgoCD / Flux</b> - self-heal and prune on policy/ and platform/ applications; runs with its own SPIFFE identity and a scoped Vault role, not cluster-admin",
          58, 690, 530, 56, GREEN, WHITE, fs=9, sw=2)
    p.box("gitNote", "The security baseline is a property of the <b>repository</b>, not the cluster. Rebuilding from Git yields the same baseline. An application out of sync beyond the agreed window is an alert.",
          608, 690, 534, 56, GREEN, GREEN_B, fs=9, sw=2)
    p.edge("e_git_adm", "zGit", "zAdm", E(GREEN, 2, dashed=True) + "exitX=0.007;exitY=0;entryX=0.007;entryY=1;", points=[(28, 652), (28, 418)])
    p.text("gitLbl", "policies and rules reconciled from Git (dashed)", 52, 420, 300, 16, GREEN, fs=8, bold=True, align="left", bg=False)
    return p


# ===========================================================================
# PAGE 7 - AI WORKLOAD SECURITY
# ===========================================================================
def page_ai_workload() -> Page:
    p = Page("p7-aiwork", "7. AI Workload Security")
    p.title("AI Workload Security - Guardrails, Detection, Red Teaming and Model Supply Chain",
            "Protects the thing the platform exists to run. Guardrails are a platform service that cannot be bypassed; red-team closure is a contractual handover gate; models are signed like images.")

    p.zone("zInf", "INFERENCE PATH", 40, 80, 1120, 190, BLUE, BLUE_F)
    inf = [
        ("i1", "<b>User / application</b><br><br>external or tenant<br>internal caller", RED, RED_F),
        ("i2", "<b>API gateway</b><br><br>authn, rate limiting,<br>extraction throttling", BLUE, WHITE),
        ("i3", "<b>Guardrails - INPUT rails</b><br><br>injection, jailbreak,<br>topic control", GREEN, GREEN_B),
        ("i4", "<b>NIM / Triton serving</b><br><br>GPU in CC mode, encrypted<br>VRAM, attested (02)", AMB, AMB_L),
        ("i5", "<b>Guardrails - OUTPUT rails</b><br><br>PII and secrets, cross-tenant<br>leakage, grounding", GREEN, GREEN_B),
        ("i6", "<b>Response</b><br><br>plus rail decision logs<br>to Morpheus and SIEM", BLUE, WHITE),
    ]
    for i, (cid, txt, stroke, fill) in enumerate(inf):
        p.box(cid, txt, 58 + i * 185, 118, 170, 84, stroke, fill, fs=9, sw=2, dashed=(cid == "i4"))
        if i: p.edge(f"e_{inf[i-1][0]}_{cid}", inf[i-1][0], cid, E(GREEN if cid in ("i3", "i4", "i5") else "#333333", 2))
    p.box("infNote", "Serving pods accept traffic <b>only</b> from the guardrails service (network policy, enforced at admission). Bypass is not a configuration option a tenant has. Tenants extend the baseline rails; they cannot reduce them. NeMo Guardrails is deployed once by the platform and consumed by every serving stack.",
          58, 214, 1085, 44, GREEN, WHITE, fs=9, sw=1)

    p.zone("zMor", "MORPHEUS - AI-DRIVEN DETECTION, scoped per tenant", 40, 290, 560, 200, PURP, PURP_F)
    p.box("morIn", "<b>Inputs</b><br><br>Guardrails decision logs<br>Inference request metadata (never content)<br>Hubble flows, DPU telemetry<br>Falco, Argus<br>Kubernetes audit, Keycloak logs", 58, 328, 240, 140, PURP, WHITE, fs=9, align="left", va="top")
    p.box("morPipe", "<b>Pipelines</b><br><br>Inference behaviour - extraction, rail-bypass probing<br>Egress anomaly - exfiltration-shaped flows<br>Host integrity - deviation from node baseline<br>Identity - misuse and escalation sequences", 318, 328, 262, 96, PURP, WHITE, fs=9, bold=False, align="left", va="top")
    p.box("morOut", "to client SIEM; optional rate-limit signal back to the gateway", 318, 432, 262, 36, PURP, PURP_F, fs=9)
    p.edge("e_morIn_pipe", "morIn", "morPipe", E(PURP, 2)); p.edge("e_pipe_out", "morPipe", "morOut", E(PURP, 2))

    p.zone("zRed", "GARAK RED-TEAM LOOP - before handover, then on change and quarterly", 620, 290, 540, 200, RED, RED_F)
    rt = [("r1", "<b>1 Scope</b><br>endpoints, rails, threat classes", 638, 328), ("r2", "<b>2 Probe</b><br>via rails AND direct from inside tenant ns", 808, 328), ("r3", "<b>3 Triage</b><br>rate against declared data sensitivity", 978, 328),
          ("r6", "<b>6 Evidence</b><br>report + acceptance into signed pack", 638, 392), ("r5", "<b>5 Close</b><br>crit/high closed or client risk-accepted", 808, 392), ("r4", "<b>4 Remediate</b><br>rail tuning, prompt hardening, policy", 978, 392)]
    for cid, txt, x, y in rt:
        p.box(cid, txt, x, y, 160, 52, RED, WHITE, fs=9)
    p.edge("e_r12", "r1", "r2", E(RED, 2)); p.edge("e_r23", "r2", "r3", E(RED, 2)); p.edge("e_r34", "r3", "r4", E(RED, 2))
    p.edge("e_r45", "r4", "r5", E(RED, 2)); p.edge("e_r56", "r5", "r6", E(RED, 2))
    p.box("redGate", "<b>HANDOVER GATE</b> - no open critical or high finding without client risk acceptance. Written into the SOW as an acceptance criterion.", 638, 452, 500, 30, STOP, STOP_F, fs=9, sw=2)

    p.zone("zModel", "MODEL SUPPLY CHAIN - same shape as images (06), different scanners, same HSM key", 40, 510, 1120, 150, GREY, GREY_F)
    ms = [("m1", "<b>Approved sources</b><br>NGC, client training pipeline, named HF orgs", GREY, WHITE), ("m2", "<b>Quarantine intake</b><br>source, version, licence, publisher sig", GREY, WHITE),
          ("m3", "<b>Format gate</b><br>safetensors / ONNX only; pickle rejected", STOP, STOP_F), ("m4", "<b>Scan</b><br>malicious serialisation, licence, behavioural eval", AMB, AMB_L),
          ("m5", "<b>Provenance + sign</b><br>in-toto attestation, cosign with HSM key", GREEN, GREEN_B), ("m6", "<b>Model registry</b><br>per-tenant projects, OCI artefacts", GREY, WHITE),
          ("m7", "<b>Admission</b><br>Kyverno: signed digest with current attestations only", BLUE, WHITE)]
    for i, (cid, txt, stroke, fill) in enumerate(ms):
        p.box(cid, txt, 58 + i * 157, 548, 144, 88, stroke, fill, fs=9, sw=2)
        if i: p.edge(f"e_{ms[i-1][0]}_{cid}", ms[i-1][0], cid, E("#333333", 2))
    p.text("modelNote", "Model weights are the highest-value artefact on the platform and the one an attacker most wants to swap. Treating them with less rigour than container images is the common mistake.",
           58, 640, 1085, 16, "#444444", fs=9, italic=True, bg=False)

    p.zone("zThreat", "GPU-AS-A-SERVICE THREAT MODEL - beyond the tenant-with-root actor in 01", 40, 680, 1120, 88, RED, RED_F)
    th = [("t1", "<b>Model theft</b><br>CC GPU, file ACL, Argus"), ("t2", "<b>Data exfiltration</b><br>Cilium egress, DPU deny, VRF"), ("t3", "<b>Prompt injection</b><br>input rails, Morpheus"),
          ("t4", "<b>Jailbreak</b><br>input rails, prompt hardening"), ("t5", "<b>Output leakage</b><br>output rails, tenant-scoped RAG"), ("t6", "<b>Supply chain</b><br>format gate, scan, sign, admit"),
          ("t7", "<b>API extraction</b><br>rate limit, entropy, Morpheus")]
    for i, (cid, txt) in enumerate(th):
        p.box(cid, txt, 58 + i * 157, 714, 144, 44, RED, WHITE, fs=9)
    return p


# ===========================================================================
# PAGE 8 - DELIVERY MODEL, SOE AND HANDOVER GATES
# ===========================================================================
def page_governance() -> Page:
    p = Page("p8-governance", "8. Reference Architecture, SOE and Governance")
    p.title("Delivery Model, Security SOE and Day 2 Handover Gates",
            "Controls are designed here and embedded as code into builds executed by other squads. The SOE makes that repeatable; four KPIs make handover testable.")

    # reference architecture band
    p.zone("zRa", "NVIDIA REFERENCE ARCHITECTURE - what the security layer is certified against", 40, 70, 1120, 96, PURP, PURP_F)
    ra = [("ra1", "<b>DGX SuperPOD</b><br>BlueField-3, ConnectX-7/8, Spectrum-X or InfiniBand, Base Command Manager"),
          ("ra2", "<b>DGX BasePOD</b><br>same component families, smaller scale - validation scope shrinks, design does not"),
          ("ra3", "<b>NCP reference</b><br>multi-tenant GPU cloud: DPF, OVN VPC, per-tenant isolation - closest match to this set"),
          ("ra4", "<b>NVIDIA AI Enterprise</b><br>supported, scanned images incl. Government Ready - the supply chain intake source")]
    for i, (cid, txt) in enumerate(ra):
        p.box(cid, txt, 58 + i * 272, 104, 258, 50, PURP, WHITE, fs=9)
    p.text("raNote", "every security tool is validated against the exact DOCA / BSP / operator / Kubernetes versions in the client build - a control that works on DOCA 3.4 and breaks on 3.5 was not validated",
           58, 152, 1085, 12, PURP, fs=8, italic=True, bg=False)

    # SOE
    p.zone("zSoe", "SECURITY SOE - versioned baseline, client variation as overlays only", 40, 186, 540, 196, GREEN, GREEN_F)
    soe = [("soe1", "<b>DPU</b><br>Restricted mode, HBN + OVS-DOCA baseline, Argus, enrolment runbook"), ("soe2", "<b>Platform</b><br>CIS profile, PSS, policies P1-P10, Cilium deny, RBAC contract"),
           ("soe3", "<b>Identity + secrets</b><br>Keycloak realm, Vault namespace + policy templates, SPIRE"), ("soe4", "<b>Supply chain</b><br>CI templates: SBOM, scan, sign, attest; registry; verifyImages"),
           ("soe5", "<b>AI workload</b><br>baseline rails, Morpheus pipelines, Garak probe profile"), ("soe6", "<b>Crypto + evidence</b><br>HSM pattern, PQ selections, validation harness, evidence schema")]
    for i, (cid, txt) in enumerate(soe):
        p.box(cid, txt, 58 + (i % 3) * 172, 224 + (i // 3) * 68, 164, 58, GREEN, GREEN_B if i % 2 == 0 else WHITE, fs=9)
    p.text("soeNote", "Every element has a version. A client need that cannot be met as an overlay is a change request against the SOE with a cost, not a silent fork.",
           58, 360, 504, 18, GREEN, fs=9, italic=True, bg=False)

    # domain interfaces
    p.zone("zDom", "DOMAIN INTERFACES - leverage is policy-as-code, gates and design authority", 640, 186, 520, 196, BLUE, BLUE_F)
    dom = [("d1", "<b>AI SECURITY</b><br>this domain<br><br>owns design, policy-as-code, gates, evidence packs, BoM, LOE", BLUE, GREEN_B, True),
           ("d2", "<b>AI PLATFORMS</b><br><br>owns K8s / OpenShift baseline; hosts and executes security manifests", BLUE, WHITE, False),
           ("d3", "<b>AI NETWORK</b><br><br>owns DPU hardware, firmware, BSP; executes DPU security services", BLUE, WHITE, False),
           ("d4", "<b>SOLUTIONS SQUADS</b><br><br>own application rail content; consume red-team findings", BLUE, WHITE, False),
           ("d5", "<b>CLIENT</b><br><br>owns IdP, SIEM / SOC, risk acceptance; may own the HSM", PURP, PURP_F, False)]
    for i, (cid, txt, stroke, fill, bold) in enumerate(dom):
        p.box(cid, txt, 652 + i * 100, 224, 94, 112, stroke, fill, fs=8, sw=2 if bold else 1, align="left", va="top")
    p.text("domNote", "Two interfaces need a written agreement, not a table row: the DPU change process with AI Network, and the RBAC group contract with the client identity team.",
           652, 344, 494, 30, BLUE, fs=9, italic=True, bg=False)
    p.edge("e_soe_dom", "zSoe", "zDom", E(GREEN, 3) + "exitX=1;exitY=0.5;entryX=0;entryY=0.5;")
    p.text("soeDomLbl", "embedded<br>as code", 582, 258, 56, 24, GREEN, fs=8, bold=True, bg=False)

    # handover gates
    p.zone("zGate", "DAY 2 HANDOVER GATES - the role's four KPIs, made testable", 40, 402, 1120, 186, GREY, GREY_F, sw=3)
    kp = [("k1", "<b>TENANCY ISOLATION</b><br>zero cross-tenant access paths<br><br><i>evidence:</i> signed pack per tenant - V1-V4 results, policy conformance diff, attestation verdicts (03)"),
          ("k2", "<b>SECURITY GATE INTEGRITY</b><br>zero unsigned / unscanned images; guardrails + detection live first<br><br><i>evidence:</i> admission reports with zero P2 exceptions, Falco + Argus alerts in client SIEM, rails loaded (06, 07)"),
          ("k3", "<b>RED-TEAM CLOSURE</b><br>all critical / high closed or client risk-accepted<br><br><i>evidence:</i> Garak report, remediation record, signed acceptance for residuals (07)"),
          ("k4", "<b>SECURITY BoM ACCURACY</b><br>entitlements validated, zero unsupported components<br><br><i>evidence:</i> BoM with support-matrix column complete for every row, client sign-off (08)")]
    for i, (cid, txt) in enumerate(kp):
        p.box(cid, txt, 58 + i * 218, 440, 206, 108, GREEN, WHITE, fs=8, sw=2, align="left", va="top")
    p.box("hand", "<b>HANDOVER</b><br><br>all four pass<br>+ crypto posture map accepted<br>+ residuals in client risk register<br>+ runbooks, SOC tabletop, transition on-call", 940, 440, 202, 108, STOP, GREEN_B, fs=8, sw=3, align="left", va="top")
    # k4 connects directly; k1-k3 drop to a shared bus under the boxes and enter the handover box from below
    p.edge("e_k4_hand", "k4", "hand", E(GREEN, 2) + "exitX=1;exitY=0.5;entryX=0;entryY=0.5;")
    for i, cid in enumerate(("k1", "k2", "k3")):
        cx = 58 + i * 218 + 103
        p.edge(f"e_{cid}_hand", cid, "hand", E(GREEN, 1) + "exitX=0.5;exitY=1;entryX=0.5;entryY=1;", points=[(cx, 562), (1041, 562)])
    p.text("gateNote", "No pass, no handover. These are SOW acceptance criteria, so they survive schedule pressure.", 58, 570, 700, 14, "#444444", fs=9, italic=True, bg=False)

    # compliance + LOE
    p.zone("zComp", "COMPLIANCE PATHWAYS the architecture is built to evidence - the client's assessor decides", 40, 598, 700, 90, AMB, AMB_L)
    cp = [("c1", "<b>Essential Eight</b><br>app control, patching, admin restriction, MFA"), ("c2", "<b>ISM</b><br>crypto, hardening, segmentation, logging, supply chain"),
          ("c3", "<b>IRAP</b><br>assessor-consumable evidence; engage early on the attestation residual"), ("c4", "<b>APRA CPS 234 / 230</b><br>asset classification, third-party controls"),
          ("c5", "<b>ISO/IEC 27001</b><br>D and R registers feed the risk treatment plan")]
    for i, (cid, txt) in enumerate(cp):
        p.box(cid, txt, 58 + i * 134, 634, 126, 44, AMB, WHITE, fs=8)
    p.zone("zLoe", "LABOUR ESTIMATE - what moves the number", 760, 598, 400, 90, GREY, GREY_F)
    p.box("loe", "tenants at go-live (isolation is per tenant) - inference endpoints (red team is per endpoint) - IdP / HSM / SIEM / GitOps: integrate or stand up - compliance pathway (IRAP adds evidence + liaison) - confidential computing scope",
          778, 634, 364, 44, GREY, WHITE, fs=8, align="left")

    p.text("foot", "This domain does not direct an engineering pool. If the SOE, the gates and the ownership table are not written down and agreed, the design authority exists only in meetings.",
           40, 702, 1120, 40, "#444444", fs=10, italic=True, bg=False)
    return p


# ===========================================================================
# Page registry - order here is tab order in draw.io
# ===========================================================================
PAGES = [page_trust_zones, page_attestation, page_isolation, page_crypto_posture,
         page_platform_identity, page_supply_chain, page_ai_workload, page_governance]


# ===========================================================================
def main(argv=None) -> int:
    here = Path(__file__).resolve().parent
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("-o", "--output", type=Path, default=here / "out" / "bluefield.drawio")
    ap.add_argument("--check", action="store_true", help="exit 1 if the checker reports errors")
    ap.add_argument("--renderer", default="auto", choices=["auto", "drawio", "builtin"])
    args = ap.parse_args(argv)

    doc = Document([fn() for fn in PAGES])
    doc.save(args.output)
    print(f"wrote {args.output}  pages={len(doc.pages)}")
    for r in render_all(str(args.output), ["svg"], renderer=args.renderer):
        print(f"wrote {os.path.basename(r.path)} ({r.renderer})")
    report = check_xml(doc.xml(), path=str(args.output))
    print(report.to_text())
    return 1 if args.check and report.errors else 0


if __name__ == "__main__":
    sys.exit(main())
