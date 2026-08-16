#!/usr/bin/env python3
"""
Seed the global_tech_stack table with the curated data center / fab dataset.
Idempotent: re-running upserts by name (replaces existing rows with the same name).
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from schema import get_connection

DATACENTERS = [
    # ── Semiconductor Equipment & Foundries ──────────────────────
    {
        "name": "ASML", "city": "Veldhoven, Netherlands", "sector": "EUV Lithography HQ",
        "lat": 51.4170, "lng": 5.4285, "marker_color": "#f472b6", "is_featured": 1,
        "tech_stack": [
            {"name": "EUV Lithography", "role": "Wafer patterning systems"},
            {"name": "KrF/ArF Lasers", "role": "Deep-UV light sources"},
            {"name": "Computational Lithography", "role": "OPC & mask optimization"},
            {"name": "ASML PAS 5500", "role": "Stepper/scanner platform"}
        ]
    },
    {
        "name": "TSMC FAB 18", "city": "Tainan Science Park, Taiwan", "sector": "Semiconductor Foundry",
        "lat": 23.1038, "lng": 120.2876, "marker_color": "#22d3ee", "is_featured": 1,
        "tech_stack": [
            {"name": "3nm FinFET", "role": "Leading-edge process node"},
            {"name": "EUV Scanner", "role": "Sub-7nm patterning"},
            {"name": "CoWoS Packaging", "role": "Advanced 2.5D integration"},
            {"name": "APC System", "role": "Real-time fab dispatch"}
        ]
    },
    {
        "name": "TSMC FAB 20", "city": "Hsinchu, Taiwan", "sector": "Semiconductor Foundry",
        "lat": 24.8100, "lng": 120.9700, "marker_color": "#06b6d4", "is_featured": 1,
        "tech_stack": [
            {"name": "2nm GAA", "role": "Next-gen gate-all-around node"},
            {"name": "High-NA EUV", "role": "Sub-2nm patterning"},
            {"name": "N3E Process", "role": "Enhanced 3nm production"},
            {"name": "SoIC Packaging", "role": "System-on-integrated-chips"}
        ]
    },
    {
        "name": "SAMSUNG HWASEONG", "city": "Hwaseong, South Korea", "sector": "Semiconductor Foundry",
        "lat": 37.2060, "lng": 126.8200, "marker_color": "#a78bfa", "is_featured": 1,
        "tech_stack": [
            {"name": "GAA Transistors", "role": "3nm gate-all-around"},
            {"name": "HBM3E", "role": "High-bandwidth memory"},
            {"name": "EUV Lithography", "role": "Node scaling"},
            {"name": "DRAM/NAND", "role": "Memory fabrication"}
        ]
    },
    {
        "name": "SAMSUNG TAYLOR", "city": "Taylor, TX", "sector": "Semiconductor Foundry",
        "lat": 30.5780, "lng": -97.4100, "marker_color": "#c084fc", "is_featured": 1,
        "tech_stack": [
            {"name": "4nm Process", "role": "Advanced logic node"},
            {"name": "EUV Lithography", "role": "Sub-7nm patterning"},
            {"name": "GAA Architecture", "role": "Gate-all-around transistors"},
            {"name": "$17B Fab", "role": "Next-gen US production"}
        ]
    },
    {
        "name": "INTEL HILLSBORO", "city": "Hillsboro, OR", "sector": "Semiconductor Foundry",
        "lat": 45.5228, "lng": -122.9898, "marker_color": "#34d399", "is_featured": 1,
        "tech_stack": [
            {"name": "Intel 18A", "role": "1.8nm RibbonFET node"},
            {"name": "High-NA EUV", "role": "Next-gen lithography"},
            {"name": "PowerVia", "role": "Backside power delivery"},
            {"name": "Foveros", "role": "3D die stacking"}
        ]
    },
    {
        "name": "INTEL CHANDLER", "city": "Chandler, AZ", "sector": "Semiconductor Foundry",
        "lat": 33.3060, "lng": -111.8400, "marker_color": "#6ee7b7", "is_featured": 1,
        "tech_stack": [
            {"name": "Intel 3 Process", "role": "High-performance node"},
            {"name": "EMIB Packaging", "role": "Embedded multi-die interconnect"},
            {"name": "Foveros", "role": "3D die stacking"},
            {"name": "RibbonFET", "role": "Gate-all-around transistor"}
        ]
    },
    {
        "name": "INTEL MAGDEBURG", "city": "Magdeburg, Germany", "sector": "Semiconductor Foundry",
        "lat": 52.1300, "lng": 11.6200, "marker_color": "#5eead4", "is_featured": 1,
        "tech_stack": [
            {"name": "Intel 18A", "role": "1.8nm node production"},
            {"name": "High-NA EUV", "role": "First High-NA EUV fab"},
            {"name": "EU Chips Act", "role": "€30B European fab initiative"},
            {"name": "RibbonFET", "role": "Next-gen transistor architecture"}
        ]
    },
    {
        "name": "GLOBALFOUNDRIES MALTA", "city": "Malta, NY", "sector": "Semiconductor Foundry",
        "lat": 42.9700, "lng": -73.7800, "marker_color": "#86efac", "is_featured": 1,
        "tech_stack": [
            {"name": "12LP/12FDX", "role": "FD-SOI & FinFET nodes"},
            {"name": "22FDX", "role": "22nm FD-SOI process"},
            {"name": "RF SOI", "role": "5G/mmWave RF switches"},
            {"name": "Bipolar CMOS", "role": "Analog/mixed-signal"}
        ]
    },
    {
        "name": "GLOBALFOUNDRIES DRESDEN", "city": "Dresden, Germany", "sector": "Semiconductor Foundry",
        "lat": 51.0500, "lng": 13.7400, "marker_color": "#a7f3d0", "is_featured": 1,
        "tech_stack": [
            {"name": "22FDX", "role": "22nm FD-SOI process"},
            {"name": "28LP", "role": "28nm planar node"},
            {"name": "Silicon Saxony", "role": "European semiconductor cluster"},
            {"name": "BCD Process", "role": "Power management ICs"}
        ]
    },
    {
        "name": "MICRON BOISE", "city": "Boise, ID", "sector": "Memory Manufacturing",
        "lat": 43.6000, "lng": -116.2000, "marker_color": "#fde047", "is_featured": 1,
        "tech_stack": [
            {"name": "HBM3E", "role": "High-bandwidth memory"},
            {"name": "1β DRAM", "role": "1-beta DRAM node"},
            {"name": "232-Layer NAND", "role": "3D NAND flash"},
            {"name": "CuA Technology", "role": "CMOS under array"}
        ]
    },
    {
        "name": "SK HYNIX ICHEON", "city": "Icheon, South Korea", "sector": "Memory Manufacturing",
        "lat": 37.2700, "lng": 127.4400, "marker_color": "#fca5a5", "is_featured": 1,
        "tech_stack": [
            {"name": "HBM3E", "role": "AI accelerator memory"},
            {"name": "1a DRAM", "role": "10nm-class DRAM"},
            {"name": "238-Layer NAND", "role": "Highest-density 3D NAND"},
            {"name": "EUV Lithography", "role": "Memory node scaling"}
        ]
    },
    {
        "name": "TEXAS INSTRUMENTS SHERMAN", "city": "Sherman, TX", "sector": "Analog Semiconductor Fab",
        "lat": 33.6400, "lng": -96.6100, "marker_color": "#fbbf24", "is_featured": 1,
        "tech_stack": [
            {"name": "45nm analog", "role": "Analog/mixed-signal process"},
            {"name": "BCD Power", "role": "Power management ICs"},
            {"name": "RF SOI", "role": "RF switch fabrication"},
            {"name": "$30B Investment", "role": "Largest US analog fab"}
        ]
    },
    # ── Hyperscale Data Centers ──────────────────────────────────
    {
        "name": "GOOGLE THE DALLES", "city": "The Dalles, OR", "sector": "Hyperscale Data Center",
        "lat": 45.6043, "lng": -121.1787, "marker_color": "#4ade80", "is_featured": 1,
        "tech_stack": [
            {"name": "Borg", "role": "Cluster workload scheduler"},
            {"name": "Kubernetes", "role": "Container orchestration"},
            {"name": "Tensor Processing Units", "role": "AI accelerator silicon"},
            {"name": "Andromeda", "role": "SDN virtual networking"}
        ]
    },
    {
        "name": "GOOGLE COUNCIL BLUFFS", "city": "Council Bluffs, IA", "sector": "Hyperscale Data Center",
        "lat": 41.2600, "lng": -95.8600, "marker_color": "#22c55e", "is_featured": 1,
        "tech_stack": [
            {"name": "Borg", "role": "Cluster scheduler"},
            {"name": "TPU v5", "role": "AI training accelerator"},
            {"name": "Jupiter Network", "role": "Petabit-scale fabric"},
            {"name": "Wind Power PPA", "role": "100% renewable energy"}
        ]
    },
    {
        "name": "GOOGLE HAMINA", "city": "Hamina, Finland", "sector": "Hyperscale Data Center",
        "lat": 60.5700, "lng": 27.1800, "marker_color": "#16a34a", "is_featured": 1,
        "tech_stack": [
            {"name": "Seawater Cooling", "role": "Gulf of Finland free cooling"},
            {"name": "Borg", "role": "Cluster scheduler"},
            {"name": "Wind Power", "role": "Nordic renewable energy"},
            {"name": "Paper Mill Retrofit", "role": "Adaptive architecture"}
        ]
    },
    {
        "name": "GOOGLE ST GHISLAIN", "city": "St Ghislain, Belgium", "sector": "Hyperscale Data Center",
        "lat": 50.4500, "lng": 3.8200, "marker_color": "#15803d", "is_featured": 1,
        "tech_stack": [
            {"name": "Borg", "role": "Cluster scheduler"},
            {"name": "Industrial Canal Cooling", "role": "River-based thermal"},
            {"name": "Wind Power", "role": "Belgian offshore wind PPA"},
            {"name": "TPU Pods", "role": "AI compute clusters"}
        ]
    },
    {
        "name": "GOOGLE SINGAPORE", "city": "Jurong, Singapore", "sector": "Hyperscale Data Center",
        "lat": 1.3500, "lng": 103.7000, "marker_color": "#166534", "is_featured": 1,
        "tech_stack": [
            {"name": "Borg", "role": "Cluster scheduler"},
            {"name": "Tropical Cooling", "role": "High-humidity optimized HVAC"},
            {"name": "TPU Pods", "role": "APAC AI compute"},
            {"name": "Submarine Cables", "role": "APAC peering hub"}
        ]
    },
    {
        "name": "META PRINEVILLE", "city": "Prineville, OR", "sector": "Hyperscale Data Center",
        "lat": 44.3000, "lng": -120.8500, "marker_color": "#60a5fa", "is_featured": 1,
        "tech_stack": [
            {"name": "F16/Hack", "role": "Backend services framework"},
            {"name": "TUPLES", "role": "Data infrastructure"},
            {"name": "Open Compute Project", "role": "Open-source hardware"},
            {"name": "Hot Aisle Containment", "role": "PUE 1.07 cooling"}
        ]
    },
    {
        "name": "META LULEÅ", "city": "Luleå, Sweden", "sector": "Hyperscale Data Center",
        "lat": 65.5800, "lng": 22.1500, "marker_color": "#3b82f6", "is_featured": 1,
        "tech_stack": [
            {"name": "F16/Hack", "role": "Backend services"},
            {"name": "Arctic Cooling", "role": "Free outside-air cooling"},
            {"name": "Hydroelectric Power", "role": "100% renewable energy"},
            {"name": "Open Compute", "role": "Custom rack designs"}
        ]
    },
    {
        "name": "META CLONEE", "city": "Clonee, Ireland", "sector": "Hyperscale Data Center",
        "lat": 53.5800, "lng": -6.4600, "marker_color": "#2563eb", "is_featured": 1,
        "tech_stack": [
            {"name": "F16/Hack", "role": "Backend services"},
            {"name": "Temperate Cooling", "role": "Irish climate free cooling"},
            {"name": "Wind Power", "role": "Irish wind farm PPA"},
            {"name": "Open Compute", "role": "Custom hardware"}
        ]
    },
    {
        "name": "META LOS LUNAS", "city": "Los Lunas, NM", "sector": "Hyperscale Data Center",
        "lat": 34.7700, "lng": -106.7300, "marker_color": "#1d4ed8", "is_featured": 1,
        "tech_stack": [
            {"name": "F16/Hack", "role": "Backend services"},
            {"name": "Solar Power", "role": "On-site solar generation"},
            {"name": "Desert Cooling", "role": "Low-humidity evaporative"},
            {"name": "AI Training Cluster", "role": "GPU infrastructure"}
        ]
    },
    {
        "name": "AWS UMATILLA", "city": "Umatilla, OR", "sector": "Hyperscale Data Center",
        "lat": 45.9200, "lng": -119.5800, "marker_color": "#fb923c", "is_featured": 1,
        "tech_stack": [
            {"name": "Nitro", "role": "Offload hypervisor card"},
            {"name": "Graviton4", "role": "Arm-based instance CPU"},
            {"name": "Trainium", "role": "AI training accelerator"},
            {"name": "Hydroelectric Power", "role": "Columbia River dams"}
        ]
    },
    {
        "name": "AWS DUBLIN", "city": "Dublin, Ireland", "sector": "Cloud Region / Edge POP",
        "lat": 53.3498, "lng": -6.2603, "marker_color": "#f97316", "is_featured": 1,
        "tech_stack": [
            {"name": "Nitro", "role": "Offload hypervisor card"},
            {"name": "Graviton", "role": "Arm-based instance CPU"},
            {"name": "Inferentia", "role": "Inference accelerator"},
            {"name": "Anycast DNS", "role": "Route 53 edge resolution"}
        ]
    },
    {
        "name": "AWS CAPE TOWN", "city": "Cape Town, South Africa", "sector": "Cloud Region / Edge POP",
        "lat": -33.9200, "lng": 18.4200, "marker_color": "#ea580c", "is_featured": 1,
        "tech_stack": [
            {"name": "Nitro", "role": "Offload hypervisor card"},
            {"name": "Graviton", "role": "Arm-based CPU"},
            {"name": "Africa Edge", "role": "First AWS Africa region"},
            {"name": "Solar Power", "role": "Renewable energy PPA"}
        ]
    },
    {
        "name": "MICROSOFT QUINCY", "city": "Quincy, WA", "sector": "Hyperscale Data Center",
        "lat": 47.2343, "lng": -119.8525, "marker_color": "#818cf8", "is_featured": 1,
        "tech_stack": [
            {"name": "Azure Stack", "role": "Cloud control plane"},
            {"name": "Maia 100", "role": "In-house AI accelerator"},
            {"name": "Cobalt 100", "role": "Arm-based CPU silicon"},
            {"name": "Hydroelectric Power", "role": "Renewable cooling supply"}
        ]
    },
    {
        "name": "MICROSOFT DES MOINES", "city": "Des Moines, IA", "sector": "Hyperscale Data Center",
        "lat": 41.5900, "lng": -93.6100, "marker_color": "#6366f1", "is_featured": 1,
        "tech_stack": [
            {"name": "Azure Stack", "role": "Cloud control plane"},
            {"name": "Wind Power", "role": "Iowa wind farm PPA"},
            {"name": "Maia 100", "role": "AI accelerator silicon"},
            {"name": "Liquid Cooling", "role": "Direct-to-chip thermal"}
        ]
    },
    {
        "name": "MICROSOFT BOYDTON", "city": "Boydton, VA", "sector": "Hyperscale Data Center",
        "lat": 36.6700, "lng": -78.3900, "marker_color": "#4f46e5", "is_featured": 1,
        "tech_stack": [
            {"name": "Azure Stack", "role": "Cloud control plane"},
            {"name": "Nuclear PPA", "role": "Carbon-free power contract"},
            {"name": "Maia 100", "role": "AI accelerator"},
            {"name": "Cobalt 100", "role": "Arm-based CPU"}
        ]
    },
    {
        "name": "APPLE MAIDEN", "city": "Maiden, NC", "sector": "Hyperscale Data Center",
        "lat": 35.5800, "lng": -81.2100, "marker_color": "#e879f9", "is_featured": 1,
        "tech_stack": [
            {"name": "Mesos", "role": "Internal cluster scheduling"},
            {"name": "Solar Farm", "role": "100% renewable 171MW solar"},
            {"name": "Fuel Cells", "role": "Biogas backup power"},
            {"name": "iCloud Infrastructure", "role": "Apple services backend"}
        ]
    },
    {
        "name": "APPLE RENO", "city": "Reno, NV", "sector": "Hyperscale Data Center",
        "lat": 39.5300, "lng": -119.8100, "marker_color": "#d946ef", "is_featured": 1,
        "tech_stack": [
            {"name": "Mesos", "role": "Cluster scheduling"},
            {"name": "Solar Array", "role": "320MW Nevada solar"},
            {"name": "Desert Cooling", "role": "Evaporative cooling"},
            {"name": "iCloud/Apple Intelligence", "role": "AI services backend"}
        ]
    },
    {
        "name": "APPLE VIBORG", "city": "Viborg, Denmark", "sector": "Hyperscale Data Center",
        "lat": 56.4500, "lng": 9.4100, "marker_color": "#c026d3", "is_featured": 1,
        "tech_stack": [
            {"name": "Mesos", "role": "Cluster scheduling"},
            {"name": "Scandinavian Wind", "role": "100% renewable power"},
            {"name": "Free Outside-Air Cooling", "role": "Nordic climate cooling"},
            {"name": "European iCloud", "role": "EU data residency"}
        ]
    },
    {
        "name": "ALIBABA ZHANGJIAKOU", "city": "Zhangjiakou, China", "sector": "Hyperscale Data Center",
        "lat": 40.8100, "lng": 114.8870, "marker_color": "#facc15", "is_featured": 1,
        "tech_stack": [
            {"name": "Apsara", "role": "Cloud operating system"},
            {"name": "XuanTie RISC-V", "role": "Open-source SoC cores"},
            {"name": "PolarDB", "role": "Cloud-native database"},
            {"name": "Wind-powered Cooling", "role": "Renewable HVAC"}
        ]
    },
    {
        "name": "TENCENT GUIZHOU", "city": "Guizhou, China", "sector": "Hyperscale Data Center",
        "lat": 26.6000, "lng": 106.7000, "marker_color": "#fde047", "is_featured": 1,
        "tech_stack": [
            {"name": "Tencent Cloud", "role": "Cloud platform"},
            {"name": "Mountain Cave DC", "role": "Geothermal cooling in cave"},
            {"name": "AI Inference", "role": "WeChat AI services"},
            {"name": "Hydroelectric Power", "role": "Karst region hydropower"}
        ]
    },
    {
        "name": "YOTTA NM1", "city": "Navi Mumbai, India", "sector": "Hyperscale Data Center",
        "lat": 19.0822, "lng": 73.0280, "marker_color": "#f87171", "is_featured": 1,
        "tech_stack": [
            {"name": "Yotta Cloud", "role": "Sovereign data platform"},
            {"name": "NVIDIA H100", "role": "GPU AI cluster"},
            {"name": "Liquid Immersion Cooling", "role": "PUE < 1.2 thermal"},
            {"name": "Tier-IV Uptime", "role": "Fault-tolerant power"}
        ]
    },
    # ── Colocation & Internet Exchange ───────────────────────────
    {
        "name": "EQUINIX ASHBURN", "city": "Ashburn, VA", "sector": "Internet Exchange / Colocation",
        "lat": 39.0438, "lng": -77.4875, "marker_color": "#f59e0b", "is_featured": 1,
        "tech_stack": [
            {"name": "Equinix Fabric", "role": "Software-defined interconnection"},
            {"name": "OpenStack", "role": "Private cloud orchestration"},
            {"name": "BGP Anycast", "role": "Global route peering"},
            {"name": "Liquid Cooling", "role": "High-density rack thermal"}
        ]
    },
    {
        "name": "EQUINIX SINGAPORE", "city": "Singapore", "sector": "Internet Exchange / Colocation",
        "lat": 1.3200, "lng": 103.8500, "marker_color": "#d97706", "is_featured": 1,
        "tech_stack": [
            {"name": "Equinix Fabric", "role": "SD interconnection"},
            {"name": "Submarine Cable Hub", "role": "APAC cable landing"},
            {"name": "SGIX Peering", "role": "Singapore internet exchange"},
            {"name": "Liquid Cooling", "role": "Tropical data center"}
        ]
    },
    {
        "name": "EQUINIX AMSTERDAM", "city": "Amsterdam, Netherlands", "sector": "Internet Exchange / Colocation",
        "lat": 52.3000, "lng": 4.9000, "marker_color": "#b45309", "is_featured": 1,
        "tech_stack": [
            {"name": "Equinix Fabric", "role": "SD interconnection"},
            {"name": "AMS-IX Peering", "role": "Amsterdam internet exchange"},
            {"name": "Submarine Cable Hub", "role": "European cable hub"},
            {"name": "Renewable PPA", "role": "100% green energy"}
        ]
    },
    {
        "name": "DIGITAL REALTY FRANKFURT", "city": "Frankfurt, Germany", "sector": "Carrier-Neutral Colocation",
        "lat": 50.1109, "lng": 8.6821, "marker_color": "#818cf8", "is_featured": 1,
        "tech_stack": [
            {"name": "ServiceBridge", "role": "Multi-cloud interconnect"},
            {"name": "DE-CIX", "role": "World's largest IX peering"},
            {"name": "Open APIs", "role": "Cross-connect automation"},
            {"name": "Renewable PPA", "role": "Carbon-free power"}
        ]
    },
    {
        "name": "DIGITAL REALTY DALLAS", "city": "Dallas, TX", "sector": "Carrier-Neutral Colocation",
        "lat": 32.8000, "lng": -96.8200, "marker_color": "#6366f1", "is_featured": 1,
        "tech_stack": [
            {"name": "ServiceBridge", "role": "Multi-cloud interconnect"},
            {"name": "DFW Carrier Hotel", "role": "South-central US hub"},
            {"name": "Data Center Alley", "role": "Plano/Richardson corridor"},
            {"name": "Solar Power", "role": "Texas renewable PPA"}
        ]
    },
    {
        "name": "SWITCH LAS VEGAS", "city": "Las Vegas, NV", "sector": "Hyperscale Colocation",
        "lat": 36.0000, "lng": -115.1700, "marker_color": "#fb7185", "is_featured": 1,
        "tech_stack": [
            {"name": "100% Renewable", "role": "Solar-powered Tier-V"},
            {"name": "TSC AI Cloud", "role": "GPUaaS platform"},
            {"name": "Tahoe-Reno 1300MW", "role": "World's largest DC campus"},
            {"name": "Thermal Testing", "role": "Patented hot-aisle TSC"}
        ]
    },
    {
        "name": "CORESITE RESTON", "city": "Reston, VA", "sector": "Carrier-Neutral Colocation",
        "lat": 38.9600, "lng": -77.3600, "marker_color": "#f0abfc", "is_featured": 1,
        "tech_stack": [
            {"name": "Open Cloud Exchange", "role": "Software-defined interconnect"},
            {"name": "MAE-East Heritage", "role": "Historic internet hub"},
            {"name": "Direct Cloud Connect", "role": "AWS/Azure/GCP onramp"},
            {"name": "100% Renewable", "role": "Wind power PPA"}
        ]
    },
    {
        "name": "NTT TOKYO", "city": "Tokyo, Japan", "sector": "Internet Exchange / Colocation",
        "lat": 35.6800, "lng": 139.6900, "marker_color": "#a5b4fc", "is_featured": 1,
        "tech_stack": [
            {"name": "NTT GIN", "role": "Global IP network"},
            {"name": "JPIX Peering", "role": "Japan internet exchange"},
            {"name": "Submarine Cable Hub", "role": "Trans-Pacific cables"},
            {"name": "Seismic Isolation", "role": "Earthquake-rated structure"}
        ]
    },
    {
        "name": "TELEHOUSE PARIS", "city": "Paris, France", "sector": "Internet Exchange / Colocation",
        "lat": 48.8700, "lng": 2.3900, "marker_color": "#c4b5fd", "is_featured": 1,
        "tech_stack": [
            {"name": "France-IX", "role": "French internet exchange"},
            {"name": "TIER III Design", "role": "Uptime certified facility"},
            {"name": "Submarine Cable Hub", "role": "European cable landing"},
            {"name": "Renewable Energy", "role": "French nuclear PPA"}
        ]
    },
    # ── Special / Notable Facilities ─────────────────────────────
    {
        "name": "BAHNHOF PIONEN", "city": "Stockholm, Sweden", "sector": "Underground Data Center",
        "lat": 59.3300, "lng": 18.0700, "marker_color": "#67e8f9", "is_featured": 1,
        "tech_stack": [
            {"name": "Vitalus Suite", "role": "Carbon-negative hydro cooling"},
            {"name": "Cold War Bunker", "role": "30m underground granite vault"},
            {"name": "German Submarine Engines", "role": "Backup diesel generators"},
            {"name": "Two-Door Airlock", "role": "Physical security barrier"}
        ]
    },
    {
        "name": "IRON MOUNTAIN BOYERS", "city": "Boyers, PA", "sector": "Underground Data Center",
        "lat": 41.2700, "lng": -80.0700, "marker_color": "#7dd3fc", "is_featured": 1,
        "tech_stack": [
            {"name": "Underground Limestone Mine", "role": "220ft below surface"},
            {"name": "Natural Cooling", "role": "Constant 55°F mine temp"},
            {"name": "Records Vault", "role": "Billions of paper records"},
            {"name": "S3 Glacier Deep Archive", "role": "Amazon cold storage"}
        ]
    },
    {
        "name": "NSA UTAH DATA CENTER", "city": "Bluffdale, UT", "sector": "Government Intelligence",
        "lat": 40.5300, "lng": -112.0000, "marker_color": "#94a3b8", "is_featured": 1,
        "tech_stack": [
            {"name": "Exabyte Storage", "role": "Surveillance data lake"},
            {"name": "Cray Supercomputers", "role": "Cryptanalysis compute"},
            {"name": "Cooling Towers", "role": "65MW power/cooling system"},
            {"name": "TEMPEST Shielding", "role": "EM emanation security"}
        ]
    },
    {
        "name": "CERN DATA CENTRE", "city": "Geneva, Switzerland", "sector": "Scientific Computing",
        "lat": 46.2300, "lng": 6.0500, "marker_color": "#7c3aed", "is_featured": 1,
        "tech_stack": [
            {"name": "WLCG", "role": "Worldwide LHC Computing Grid"},
            {"name": "OpenStack", "role": "70,000+ core cloud"},
            {"name": "Ceph Storage", "role": "Exabyte-scale object store"},
            {"name": "HTCondor", "role": "High-throughput job scheduler"}
        ]
    },
    {
        "name": "ORACLE ABU DHABI", "city": "Abu Dhabi, UAE", "sector": "Cloud Region / Sovereign Cloud",
        "lat": 24.4539, "lng": 54.3773, "marker_color": "#2dd4bf", "is_featured": 1,
        "tech_stack": [
            {"name": "OCI", "role": "Oracle Cloud Infrastructure"},
            {"name": "Autonomous Database", "role": "Self-driving DB"},
            {"name": "Exadata", "role": "Converged database machine"},
            {"name": "Sovereign Data Zone", "role": "Data residency control"}
        ]
    },
]


def main():
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS global_tech_stack (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            city TEXT,
            sector TEXT,
            lat REAL NOT NULL,
            lng REAL NOT NULL,
            marker_color TEXT,
            is_featured INTEGER NOT NULL DEFAULT 0,
            tech_stack TEXT,
            source TEXT NOT NULL DEFAULT 'curated',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
    """)
    # Clean up ALL previously-featured entries so renamed data centers
    # (e.g. "EQUINIX DC1" -> "EQUINIX ASHBURN") don't linger as duplicates.
    conn.execute("DELETE FROM global_tech_stack WHERE is_featured = 1")
    for dc in DATACENTERS:
        conn.execute("DELETE FROM global_tech_stack WHERE name = ?", (dc["name"],))
        conn.execute("""
            INSERT INTO global_tech_stack (name, city, sector, lat, lng, marker_color, is_featured, tech_stack, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'curated')
        """, (
            dc["name"], dc["city"], dc["sector"], dc["lat"], dc["lng"],
            dc["marker_color"], dc["is_featured"], json.dumps(dc["tech_stack"])
        ))
    conn.commit()
    count = conn.execute("SELECT COUNT(*) FROM global_tech_stack").fetchone()[0]
    featured = conn.execute("SELECT COUNT(*) FROM global_tech_stack WHERE is_featured=1").fetchone()[0]
    conn.close()
    print(f"Seeded global_tech_stack: {count} total rows, {featured} featured (map markers)")


if __name__ == "__main__":
    main()
