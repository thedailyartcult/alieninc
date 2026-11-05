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

    # ── Comprehensive Pax Silica + WAICO Facilities ──────────────────
    # Extended global datacenter / fab coverage associated with both blocs,
    # following the same design language: UPPERCASE operator+location name,
    # controlled sector vocabulary, city-level coordinates, Tailwind marker
    # colors, and a 3-4 entry tech_stack describing real operations.

    # ····· HyperScale Cloud — additional Google (Pax) ·····
    {
        "name": "GOOGLE MONCKS CORNER", "city": "Moncks Corner, SC", "sector": "Hyperscale Data Center",
        "lat": 33.0641, "lng": -80.0434, "marker_color": "#22c55e", "is_featured": 1,
        "tech_stack": [
            {"name": "Borg", "role": "Cluster workload scheduler"},
            {"name": "TPU Pods", "role": "AI compute clusters"},
            {"name": "Nuclear PPA", "role": "Carbon-free power"},
            {"name": "Jupiter Fabric", "role": "Petabit network"}
        ]
    },
    {
        "name": "GOOGLE CLARKSVILLE", "city": "Clarksville, TN", "sector": "Hyperscale Data Center",
        "lat": 36.6212, "lng": -87.2631, "marker_color": "#4ade80", "is_featured": 1,
        "tech_stack": [
            {"name": "Borg", "role": "Cluster scheduler"},
            {"name": "TPU v5e", "role": "AI training accelerator"},
            {"name": "Wind PPA", "role": "Renewable power"},
            {"name": "HVDC", "role": "High-voltage DC distribution"}
        ]
    },
    {
        "name": "GOOGLE DOUGLAS COUNTY", "city": "Atlanta, GA", "sector": "Hyperscale Data Center",
        "lat": 33.7497, "lng": -84.5848, "marker_color": "#16a34a", "is_featured": 1,
        "tech_stack": [
            {"name": "Borg", "role": "Cluster scheduler"},
            {"name": "US-Southeast Region", "role": "us-southeast1"},
            {"name": "TPU Pods", "role": "AI compute"},
            {"name": "Renewable PPA", "role": "Georgia solar"}
        ]
    },
    {
        "name": "GOOGLE MAYES COUNTY", "city": "Pryor Creek, OK", "sector": "Hyperscale Data Center",
        "lat": 36.2411, "lng": -95.3301, "marker_color": "#15803d", "is_featured": 1,
        "tech_stack": [
            {"name": "Borg", "role": "Cluster scheduler"},
            {"name": "MidAmerica Campus", "role": "Industrial park co-location"},
            {"name": "Wind Power", "role": "Oklahoma renewable PPA"},
            {"name": "TPU Pods", "role": "AI compute"}
        ]
    },
    {
        "name": "GOOGLE FORT WAYNE", "city": "Fort Wayne, IN", "sector": "Hyperscale Data Center",
        "lat": 41.0793, "lng": -85.1394, "marker_color": "#22c55e", "is_featured": 1,
        "tech_stack": [
            {"name": "Borg", "role": "Cluster scheduler"},
            {"name": "TPU v5p", "role": "AI training cluster"},
            {"name": "Wind PPA", "role": "Indiana renewable"},
            {"name": "Liquid Cooling", "role": "Direct-to-chip thermal"}
        ]
    },
    {
        "name": "GOOGLE SALT LAKE CITY", "city": "Salt Lake City, UT", "sector": "Hyperscale Data Center",
        "lat": 40.7608, "lng": -111.8910, "marker_color": "#4ade80", "is_featured": 1,
        "tech_stack": [
            {"name": "Borg", "role": "Cluster scheduler"},
            {"name": "US-West3", "role": "us-west3 region"},
            {"name": "TPU Pods", "role": "AI compute"},
            {"name": "Geothermal", "role": "Intermountain power"}
        ]
    },
    {
        "name": "GOOGLE HENDERSON", "city": "Henderson, NV", "sector": "Hyperscale Data Center",
        "lat": 36.0556, "lng": -115.0102, "marker_color": "#16a34a", "is_featured": 1,
        "tech_stack": [
            {"name": "Borg", "role": "Cluster scheduler"},
            {"name": "US-West4", "role": "us-west4 region"},
            {"name": "Solar Power", "role": "Nevada solar PPA"},
            {"name": "TPU Pods", "role": "AI compute"}
        ]
    },

    # ····· HyperScale Cloud — additional Microsoft (Pax) ·····
    {
        "name": "MICROSOFT SAN ANTONIO", "city": "San Antonio, TX", "sector": "Hyperscale Data Center",
        "lat": 29.4241, "lng": -98.4936, "marker_color": "#818cf8", "is_featured": 1,
        "tech_stack": [
            {"name": "Azure Stack", "role": "Cloud control plane"},
            {"name": "Maia 100", "role": "AI accelerator"},
            {"name": "Solar PPA", "role": "Texas renewable"},
            {"name": "Liquid Cooling", "role": "Direct-to-chip"}
        ]
    },
    {
        "name": "MICROSOFT GOODYEAR", "city": "Goodyear, AZ", "sector": "Hyperscale Data Center",
        "lat": 33.4353, "lng": -112.3582, "marker_color": "#6366f1", "is_featured": 1,
        "tech_stack": [
            {"name": "Azure Stack", "role": "Cloud control plane"},
            {"name": "AI Hub", "role": "143MW AI campus"},
            {"name": "Solar Power", "role": "Arizona desert solar"},
            {"name": "Cobalt 100", "role": "Arm-based CPU"}
        ]
    },
    {
        "name": "MICROSOFT MECKLENBURG", "city": "South Hill, VA", "sector": "Hyperscale Data Center",
        "lat": 36.7265, "lng": -78.1289, "marker_color": "#4f46e5", "is_featured": 1,
        "tech_stack": [
            {"name": "Azure Stack", "role": "Cloud control plane"},
            {"name": "Nuclear PPA", "role": "Carbon-free power"},
            {"name": "Maia 100", "role": "AI accelerator"},
            {"name": "Liquid Cooling", "role": "High-density thermal"}
        ]
    },
    {
        "name": "MICROSOFT QUINLAN", "city": "Quinlan, TX", "sector": "Hyperscale Data Center",
        "lat": 32.9126, "lng": -96.1341, "marker_color": "#818cf8", "is_featured": 1,
        "tech_stack": [
            {"name": "Azure Stack", "role": "Cloud control plane"},
            {"name": "Solar PPA", "role": "Texas renewable"},
            {"name": "Maia 100", "role": "AI accelerator"},
            {"name": "Cobalt 100", "role": "Arm-based CPU"}
        ]
    },
    {
        "name": "MICROSOFT CHEYENNE", "city": "Cheyenne, WY", "sector": "Hyperscale Data Center",
        "lat": 41.1400, "lng": -104.8202, "marker_color": "#6366f1", "is_featured": 1,
        "tech_stack": [
            {"name": "Azure Stack", "role": "Cloud control plane"},
            {"name": "Wind PPA", "role": "Wyoming wind"},
            {"name": "Cobalt 100", "role": "Arm-based CPU"},
            {"name": "Maia 100", "role": "AI accelerator"}
        ]
    },
    {
        "name": "MICROSOFT DUBLIN", "city": "Dublin, Ireland", "sector": "Cloud Region / Edge POP",
        "lat": 53.3498, "lng": -6.2603, "marker_color": "#4f46e5", "is_featured": 1,
        "tech_stack": [
            {"name": "Azure Stack", "role": "Cloud control plane"},
            {"name": "Europe North", "role": "eu-west region"},
            {"name": "Wind PPA", "role": "Irish wind"},
            {"name": "Maia 100", "role": "AI accelerator"}
        ]
    },
    {
        "name": "MICROSOFT AMSTERDAM", "city": "Amsterdam, Netherlands", "sector": "Cloud Region / Edge POP",
        "lat": 52.3676, "lng": 4.9041, "marker_color": "#818cf8", "is_featured": 1,
        "tech_stack": [
            {"name": "Azure Stack", "role": "Cloud control plane"},
            {"name": "West Europe", "role": "eu-west region"},
            {"name": "Offshore Wind", "role": "Dutch renewable PPA"},
            {"name": "Cobalt 100", "role": "Arm-based CPU"}
        ]
    },

    # ····· HyperScale Cloud — additional AWS regions (Pax) ·····
    {
        "name": "AMAZON ASHBURN", "city": "Ashburn, VA", "sector": "Cloud Region / Edge POP",
        "lat": 39.0438, "lng": -77.4874, "marker_color": "#fb923c", "is_featured": 1,
        "tech_stack": [
            {"name": "Nitro", "role": "Offload hypervisor"},
            {"name": "Graviton4", "role": "Arm CPU"},
            {"name": "us-east-1", "role": "Largest AWS region"},
            {"name": "Trainium2", "role": "AI training"}
        ]
    },
    {
        "name": "AMAZON BOARDMAN", "city": "Boardman, OR", "sector": "Hyperscale Data Center",
        "lat": 45.8401, "lng": -119.7006, "marker_color": "#f97316", "is_featured": 1,
        "tech_stack": [
            {"name": "Nitro", "role": "Offload hypervisor"},
            {"name": "Graviton", "role": "Arm CPU"},
            {"name": "Hydroelectric", "role": "Columbia River power"},
            {"name": "Trainium", "role": "AI accelerator"}
        ]
    },
    {
        "name": "AMAZON COLUMBUS", "city": "Columbus, OH", "sector": "Cloud Region / Edge POP",
        "lat": 39.9612, "lng": -82.9988, "marker_color": "#fb923c", "is_featured": 1,
        "tech_stack": [
            {"name": "Nitro", "role": "Offload hypervisor"},
            {"name": "us-east-2", "role": "Ohio region"},
            {"name": "Graviton4", "role": "Arm CPU"},
            {"name": "Trainium2", "role": "AI training"}
        ]
    },
    {
        "name": "AMAZON TOKYO", "city": "Tokyo, Japan", "sector": "Cloud Region / Edge POP",
        "lat": 35.6762, "lng": 139.6503, "marker_color": "#ea580c", "is_featured": 1,
        "tech_stack": [
            {"name": "Nitro", "role": "Offload hypervisor"},
            {"name": "ap-northeast-1", "role": "Japan region"},
            {"name": "Graviton", "role": "Arm CPU"},
            {"name": "Inferentia", "role": "Inference accelerator"}
        ]
    },
    {
        "name": "AMAZON FRANKFURT", "city": "Frankfurt, Germany", "sector": "Cloud Region / Edge POP",
        "lat": 50.1109, "lng": 8.6821, "marker_color": "#f97316", "is_featured": 1,
        "tech_stack": [
            {"name": "Nitro", "role": "Offload hypervisor"},
            {"name": "eu-central-1", "role": "Germany region"},
            {"name": "Graviton4", "role": "Arm CPU"},
            {"name": "Trainium2", "role": "AI training"}
        ]
    },
    {
        "name": "AMAZON LONDON", "city": "London, UK", "sector": "Cloud Region / Edge POP",
        "lat": 51.5074, "lng": -0.1278, "marker_color": "#ea580c", "is_featured": 1,
        "tech_stack": [
            {"name": "Nitro", "role": "Offload hypervisor"},
            {"name": "eu-west-2", "role": "UK region"},
            {"name": "Graviton", "role": "Arm CPU"},
            {"name": "Inferentia", "role": "Inference accelerator"}
        ]
    },
    {
        "name": "AMAZON PARIS", "city": "Paris, France", "sector": "Cloud Region / Edge POP",
        "lat": 48.8566, "lng": 2.3522, "marker_color": "#f97316", "is_featured": 1,
        "tech_stack": [
            {"name": "Nitro", "role": "Offload hypervisor"},
            {"name": "eu-west-3", "role": "France region"},
            {"name": "Nuclear Grid", "role": "French low-carbon power"},
            {"name": "Graviton4", "role": "Arm CPU"}
        ]
    },
    {
        "name": "AMAZON STOCKHOLM", "city": "Stockholm, Sweden", "sector": "Cloud Region / Edge POP",
        "lat": 59.3293, "lng": 18.0686, "marker_color": "#fb923c", "is_featured": 1,
        "tech_stack": [
            {"name": "Nitro", "role": "Offload hypervisor"},
            {"name": "eu-north-1", "role": "Sweden region"},
            {"name": "Hydroelectric", "role": "Nordic renewable"},
            {"name": "Graviton", "role": "Arm CPU"}
        ]
    },
    {
        "name": "AMAZON SYDNEY", "city": "Sydney, Australia", "sector": "Cloud Region / Edge POP",
        "lat": -33.8688, "lng": 151.2093, "marker_color": "#ea580c", "is_featured": 1,
        "tech_stack": [
            {"name": "Nitro", "role": "Offload hypervisor"},
            {"name": "ap-southeast-2", "role": "Australia region"},
            {"name": "Solar PPA", "role": "Australian renewable"},
            {"name": "Graviton", "role": "Arm CPU"}
        ]
    },
    {
        "name": "AMAZON MUMBAI", "city": "Mumbai, India", "sector": "Cloud Region / Edge POP",
        "lat": 19.0760, "lng": 72.8777, "marker_color": "#f97316", "is_featured": 1,
        "tech_stack": [
            {"name": "Nitro", "role": "Offload hypervisor"},
            {"name": "ap-south-1", "role": "India region"},
            {"name": "Graviton4", "role": "Arm CPU"},
            {"name": "Solar PPA", "role": "Indian renewable"}
        ]
    },
    {
        "name": "AMAZON SEOUL", "city": "Seoul, South Korea", "sector": "Cloud Region / Edge POP",
        "lat": 37.5665, "lng": 126.9780, "marker_color": "#ea580c", "is_featured": 1,
        "tech_stack": [
            {"name": "Nitro", "role": "Offload hypervisor"},
            {"name": "ap-northeast-2", "role": "Korea region"},
            {"name": "Graviton4", "role": "Arm CPU"},
            {"name": "Trainium2", "role": "AI training"}
        ]
    },
    {
        "name": "AMAZON SAO PAULO", "city": "São Paulo, Brazil", "sector": "Cloud Region / Edge POP",
        "lat": -23.5505, "lng": -46.6333, "marker_color": "#fb923c", "is_featured": 1,
        "tech_stack": [
            {"name": "Nitro", "role": "Offload hypervisor"},
            {"name": "sa-east-1", "role": "Brazil region"},
            {"name": "Graviton", "role": "Arm CPU"},
            {"name": "Hydroelectric", "role": "Brazilian renewable"}
        ]
    },

    # ····· HyperScale Cloud — additional Meta (Pax) ·····
    {
        "name": "META FORT WORTH", "city": "Fort Worth, TX", "sector": "Hyperscale Data Center",
        "lat": 32.7555, "lng": -97.3308, "marker_color": "#60a5fa", "is_featured": 1,
        "tech_stack": [
            {"name": "F16/Hack", "role": "Backend services"},
            {"name": "Open Compute", "role": "Custom hardware"},
            {"name": "Wind PPA", "role": "Texas renewable"},
            {"name": "AI Training", "role": "GPU infrastructure"}
        ]
    },
    {
        "name": "META ALTOONA", "city": "Altoona, IA", "sector": "Hyperscale Data Center",
        "lat": 41.6500, "lng": -93.4647, "marker_color": "#3b82f6", "is_featured": 1,
        "tech_stack": [
            {"name": "F16/Hack", "role": "Backend services"},
            {"name": "Open Compute", "role": "Custom racks"},
            {"name": "Wind PPA", "role": "Iowa wind"},
            {"name": "Hot Aisle Containment", "role": "Efficient cooling"}
        ]
    },
    {
        "name": "META NEW ALBANY", "city": "New Albany, OH", "sector": "Hyperscale Data Center",
        "lat": 40.0812, "lng": -82.8088, "marker_color": "#2563eb", "is_featured": 1,
        "tech_stack": [
            {"name": "F16/Hack", "role": "Backend services"},
            {"name": "Open Compute", "role": "Custom hardware"},
            {"name": "Solar PPA", "role": "Ohio renewable"},
            {"name": "AI Training", "role": "GPU clusters"}
        ]
    },
    {
        "name": "META DEKALB", "city": "DeKalb, IL", "sector": "Hyperscale Data Center",
        "lat": 41.9295, "lng": -88.7504, "marker_color": "#1d4ed8", "is_featured": 1,
        "tech_stack": [
            {"name": "F16/Hack", "role": "Backend services"},
            {"name": "Open Compute", "role": "Custom racks"},
            {"name": "Wind PPA", "role": "Illinois wind"},
            {"name": "AI Training", "role": "GPU infrastructure"}
        ]
    },
    {
        "name": "META ODENSE", "city": "Odense, Denmark", "sector": "Hyperscale Data Center",
        "lat": 55.4038, "lng": 10.4024, "marker_color": "#60a5fa", "is_featured": 1,
        "tech_stack": [
            {"name": "F16/Hack", "role": "Backend services"},
            {"name": "Open Compute", "role": "Custom hardware"},
            {"name": "Offshore Wind", "role": "Danish renewable"},
            {"name": "Free-Air Cooling", "role": "Nordic climate"}
        ]
    },

    # ····· HyperScale Cloud — additional Apple (Pax) ·····
    {
        "name": "APPLE WAUKE", "city": "Waukee, IA", "sector": "Hyperscale Data Center",
        "lat": 41.6117, "lng": -93.8852, "marker_color": "#e879f9", "is_featured": 1,
        "tech_stack": [
            {"name": "Mesos", "role": "Cluster scheduling"},
            {"name": "Wind PPA", "role": "Iowa renewable"},
            {"name": "iCloud Infrastructure", "role": "Apple services"},
            {"name": "Free-Air Cooling", "role": "Efficient thermal"}
        ]
    },
    {
        "name": "APPLE MESA", "city": "Mesa, AZ", "sector": "Hyperscale Data Center",
        "lat": 33.4152, "lng": -111.8315, "marker_color": "#d946ef", "is_featured": 1,
        "tech_stack": [
            {"name": "Sapphire Facility", "role": "Former GT Advanced plant"},
            {"name": "Solar Power", "role": "Arizona solar"},
            {"name": "iCloud", "role": "Apple services backend"},
            {"name": "Desert Cooling", "role": "Evaporative cooling"}
        ]
    },

    # ····· HyperScale Cloud — additional WAICO (China) hyperscale ·····
    {
        "name": "ALIBABA ULANQAB", "city": "Ulanqab, Inner Mongolia", "sector": "Hyperscale Data Center",
        "lat": 40.9925, "lng": 113.1323, "marker_color": "#facc15", "is_featured": 1,
        "tech_stack": [
            {"name": "Apsara", "role": "Cloud operating system"},
            {"name": "XuanTie RISC-V", "role": "Open-source SoC"},
            {"name": "Wind-powered Cooling", "role": "Renewable HVAC"},
            {"name": "PolarDB", "role": "Cloud database"}
        ]
    },
    {
        "name": "ALIBABA GUIYANG", "city": "Guiyang, Guizhou", "sector": "Hyperscale Data Center",
        "lat": 26.6477, "lng": 106.6302, "marker_color": "#fde047", "is_featured": 1,
        "tech_stack": [
            {"name": "Apsara", "role": "Cloud operating system"},
            {"name": "Cool Climate", "role": "Karst cave cooling"},
            {"name": "National Hub", "role": "Guizhou computing hub"},
            {"name": "PolarDB", "role": "Cloud database"}
        ]
    },
    {
        "name": "TENCENT ULANQAB", "city": "Ulanqab, Inner Mongolia", "sector": "Hyperscale Data Center",
        "lat": 40.9925, "lng": 113.1323, "marker_color": "#facc15", "is_featured": 1,
        "tech_stack": [
            {"name": "Tencent Cloud", "role": "Cloud platform"},
            {"name": "AI Inference", "role": "WeChat AI services"},
            {"name": "Wind-powered Cooling", "role": "Renewable HVAC"},
            {"name": "National Hub", "role": "Inner Mongolia hub"}
        ]
    },
    {
        "name": "TENCENT TIANJIN", "city": "Tianjin", "sector": "Hyperscale Data Center",
        "lat": 39.3434, "lng": 117.3616, "marker_color": "#fde047", "is_featured": 1,
        "tech_stack": [
            {"name": "Tencent Cloud", "role": "Cloud platform"},
            {"name": "Binhai Campus", "role": "North China hub"},
            {"name": "AI Training", "role": "GPU clusters"},
            {"name": "Renewable PPA", "role": "Green power"}
        ]
    },
    {
        "name": "BAIDU YANGQUAN", "city": "Yangquan, Shanxi", "sector": "Hyperscale Data Center",
        "lat": 37.8567, "lng": 113.5803, "marker_color": "#eab308", "is_featured": 1,
        "tech_stack": [
            {"name": "Baidu Cloud", "role": "Cloud platform"},
            {"name": "Kunlun Chip", "role": "AI accelerator"},
            {"name": "Cool Climate", "role": "Shanxi cooling"},
            {"name": "Ernie Bot", "role": "LLM inference"}
        ]
    },
    {
        "name": "HUAWEI GUIAN", "city": "Guiyang, Guizhou", "sector": "Hyperscale Data Center",
        "lat": 26.4500, "lng": 106.5100, "marker_color": "#dc2626", "is_featured": 1,
        "tech_stack": [
            {"name": "Huawei Cloud", "role": "Cloud platform"},
            {"name": "Ascend 910", "role": "AI accelerator"},
            {"name": "Guian Campus", "role": "Huge data campus"},
            {"name": "Cool Climate", "role": "Guizhou cooling"}
        ]
    },
    {
        "name": "BYTEDANCE HUAIBEI", "city": "Huaibei, Anhui", "sector": "Hyperscale Data Center",
        "lat": 33.9538, "lng": 116.7987, "marker_color": "#f87171", "is_featured": 1,
        "tech_stack": [
            {"name": "Volcano Engine", "role": "Cloud platform"},
            {"name": "Doubao LLM", "role": "AI inference"},
            {"name": "Cool Climate", "role": "Anhui cooling"},
            {"name": "GPU Clusters", "role": "Training compute"}
        ]
    },

    # ····· HyperScale Cloud — additional Asia colo/sovereign (Pax) ·····
    {
        "name": "NAVER DCC GAK", "city": "Chuncheon, South Korea", "sector": "Hyperscale Data Center",
        "lat": 37.8813, "lng": 127.7298, "marker_color": "#22d3ee", "is_featured": 1,
        "tech_stack": [
            {"name": "Naver Cloud", "role": "Cloud platform"},
            {"name": "HyperClova", "role": "LLM inference"},
            {"name": "Water-cooling", "role": "Mountain cold source"},
            {"name": "Battery Storage", "role": "On-site UPS"}
        ]
    },

    # ····· Colocation & IX — additional Pax carriers/IX ·····
    {
        "name": "EQUINIX CHICAGO", "city": "Chicago, IL", "sector": "Internet Exchange / Colocation",
        "lat": 41.8781, "lng": -87.6298, "marker_color": "#f59e0b", "is_featured": 1,
        "tech_stack": [
            {"name": "Equinix Fabric", "role": "SD interconnection"},
            {"name": "Equinix IX Chicago", "role": "Midwest peering"},
            {"name": "Carrier Hotel", "role": "350 E Cermak"},
            {"name": "Renewable PPA", "role": "Green power"}
        ]
    },
    {
        "name": "EQUINIX DALLAS", "city": "Dallas, TX", "sector": "Internet Exchange / Colocation",
        "lat": 32.7767, "lng": -96.7970, "marker_color": "#d97706", "is_featured": 1,
        "tech_stack": [
            {"name": "Equinix Fabric", "role": "SD interconnection"},
            {"name": "Equinix IX Dallas", "role": "South-central peering"},
            {"name": "Carrier Hotel", "role": "Southhall hub"},
            {"name": "Renewable PPA", "role": "Texas green"}
        ]
    },
    {
        "name": "EQUINIX LONDON", "city": "London, UK", "sector": "Internet Exchange / Colocation",
        "lat": 51.5074, "lng": -0.1278, "marker_color": "#b45309", "is_featured": 1,
        "tech_stack": [
            {"name": "Equinix Fabric", "role": "SD interconnection"},
            {"name": "LINX Peering", "role": "London internet exchange"},
            {"name": "LD4/LD5 Campuses", "role": "Docklands hub"},
            {"name": "Renewable PPA", "role": "UK green power"}
        ]
    },
    {
        "name": "DIGITAL REALTY CHICAGO", "city": "Chicago, IL", "sector": "Carrier-Neutral Colocation",
        "lat": 41.8781, "lng": -87.6298, "marker_color": "#818cf8", "is_featured": 1,
        "tech_stack": [
            {"name": "ServiceBridge", "role": "Multi-cloud interconnect"},
            {"name": "Carrier Hotel", "role": "Elmhurst campus"},
            {"name": "Open APIs", "role": "Cross-connect automation"},
            {"name": "Renewable PPA", "role": "Green power"}
        ]
    },
    {
        "name": "CORESITE LOS ANGELES", "city": "El Segundo, CA", "sector": "Carrier-Neutral Colocation",
        "lat": 33.9192, "lng": -118.4165, "marker_color": "#f0abfc", "is_featured": 1,
        "tech_stack": [
            {"name": "Open Cloud Exchange", "role": "SD interconnect"},
            {"name": "One Wilshire", "role": "LA carrier hotel"},
            {"name": "Trans-Pacific Hub", "role": "Submarine cable landing"},
            {"name": "100% Renewable", "role": "Green power"}
        ]
    },
    {
        "name": "NEXTDC SYDNEY", "city": "Sydney, Australia", "sector": "Hyperscale Colocation",
        "lat": -33.8688, "lng": 151.2093, "marker_color": "#a78bfa", "is_featured": 1,
        "tech_stack": [
            {"name": "DC Connect", "role": "Interconnect fabric"},
            {"name": "S1-S3 Campuses", "role": "Sydney hub"},
            {"name": "Hyperscale Suites", "role": "Cloud onramp"},
            {"name": "Solar PPA", "role": "Australian renewable"}
        ]
    },
    {
        "name": "ST TELEMEDIA SINGAPORE", "city": "Singapore", "sector": "Carrier-Neutral Colocation",
        "lat": 1.3347, "lng": 103.8838, "marker_color": "#c4b5fd", "is_featured": 1,
        "tech_stack": [
            {"name": "Carrier Neutral", "role": "Multi-carrier hub"},
            {"name": "Submarine Hub", "role": "APAC cable landing"},
            {"name": "Green Data Centre", "role": "Singapore sustainability"},
            {"name": "Cloud Connect", "role": "Direct onramp"}
        ]
    },
    {
        "name": "ADANICONNEX CHENNAI", "city": "Chennai, India", "sector": "Hyperscale Colocation",
        "lat": 13.0827, "lng": 80.2707, "marker_color": "#fb923c", "is_featured": 1,
        "tech_stack": [
            {"name": "AdaniConneX", "role": "JV colocation"},
            {"name": "Hyperscale Build", "role": "Edge+hyperscale"},
            {"name": "Solar PPA", "role": "Indian renewable"},
            {"name": "Tier-III Design", "role": "Uptime certified"}
        ]
    },
    {
        "name": "CTRLS HYDERABAD", "city": "Hyderabad, India", "sector": "Carrier-Neutral Colocation",
        "lat": 17.3850, "lng": 78.4867, "marker_color": "#f59e0b", "is_featured": 1,
        "tech_stack": [
            {"name": "Carrier Neutral", "role": "Multi-carrier hub"},
            {"name": "Tier-IV Uptime", "role": "Fault-tolerant power"},
            {"name": "Sovereign Cloud", "role": "Indian data residency"},
            {"name": "Green Power", "role": "Renewable PPA"}
        ]
    },
    {
        "name": "NTT OOTEMACHI", "city": "Chiyoda, Tokyo", "sector": "Internet Exchange / Colocation",
        "lat": 35.6854, "lng": 139.7646, "marker_color": "#a5b4fc", "is_featured": 1,
        "tech_stack": [
            {"name": "NTT GIN", "role": "Global IP network"},
            {"name": "JPIX Peering", "role": "Tokyo IX"},
            {"name": "Otemachi Hub", "role": "Tokyo carrier hotel"},
            {"name": "Seismic Isolation", "role": "Earthquake-rated"}
        ]
    },
    {
        "name": "KDDI OTEMACHI", "city": "Chiyoda, Tokyo", "sector": "Internet Exchange / Colocation",
        "lat": 35.6854, "lng": 139.7646, "marker_color": "#c4b5fd", "is_featured": 1,
        "tech_stack": [
            {"name": "KDDI Carrier", "role": "Telecom colocation"},
            {"name": "JPIX Peering", "role": "Tokyo IX"},
            {"name": "Submarine Hub", "role": "Trans-Pacific cables"},
            {"name": "Seismic Isolation", "role": "Earthquake-rated"}
        ]
    },

    # ····· Foundries & Fabs — additional Pax (Taiwan/Korea/Japan/US/EU) ·····
    {
        "name": "TSMC FAB 6", "city": "Shanhua, Tainan", "sector": "Semiconductor Foundry",
        "lat": 23.1101, "lng": 120.2735, "marker_color": "#22d3ee", "is_featured": 1,
        "tech_stack": [
            {"name": "7nm/5nm", "role": "Advanced logic node"},
            {"name": "EUV Lithography", "role": "Sub-7nm patterning"},
            {"name": "CoWoS", "role": "Advanced packaging"},
            {"name": "GigaFab", "role": "High-volume production"}
        ]
    },
    {
        "name": "TSMC FAB 15", "city": "Taichung", "sector": "Semiconductor Foundry",
        "lat": 24.2115, "lng": 120.6173, "marker_color": "#06b6d4", "is_featured": 1,
        "tech_stack": [
            {"name": "28nm-5nm", "role": "Advanced logic node"},
            {"name": "EUV Lithography", "role": "Sub-7nm patterning"},
            {"name": "InFO Packaging", "role": "Fan-out integration"},
            {"name": "GigaFab", "role": "High-volume production"}
        ]
    },
    {
        "name": "TSMC FAB 21", "city": "Kikuyo, Kumamoto", "sector": "Semiconductor Foundry",
        "lat": 32.8498, "lng": 130.8015, "marker_color": "#0891b2", "is_featured": 1,
        "tech_stack": [
            {"name": "JASM", "role": "Japan Advanced Semi"},
            {"name": "22/28nm", "role": "Mature logic node"},
            {"name": "Japan Expansion", "role": "Kumamoto campus"},
            {"name": "Sony Partnership", "role": "CIS integration"}
        ]
    },
    {
        "name": "TSMC FAB 22", "city": "Kaohsiung", "sector": "Semiconductor Foundry",
        "lat": 22.7097, "lng": 120.3122, "marker_color": "#22d3ee", "is_featured": 1,
        "tech_stack": [
            {"name": "28nm/22nm", "role": "Specialty logic node"},
            {"name": "Specialty Process", "role": "Mature nodes"},
            {"name": "CoWoS", "role": "Advanced packaging"},
            {"name": "GigaFab", "role": "High-volume production"}
        ]
    },
    {
        "name": "SAMSUNG PYEONGTAEK", "city": "Pyeongtaek, South Korea", "sector": "Semiconductor Foundry",
        "lat": 36.9922, "lng": 127.1125, "marker_color": "#a78bfa", "is_featured": 1,
        "tech_stack": [
            {"name": "GAA Transistors", "role": "3nm gate-all-around"},
            {"name": "HBM4", "role": "High-bandwidth memory"},
            {"name": "P2/P3 Lines", "role": "World's largest fab"},
            {"name": "EUV Lithography", "role": "Node scaling"}
        ]
    },
    {
        "name": "SAMSUNG GIHEUNG", "city": "Yongin, South Korea", "sector": "Semiconductor Foundry",
        "lat": 37.2414, "lng": 127.1777, "marker_color": "#c084fc", "is_featured": 1,
        "tech_stack": [
            {"name": "DRAM/NAND", "role": "Memory fabrication"},
            {"name": "Foundry Lines", "role": "Logic production"},
            {"name": "EUV Lithography", "role": "Advanced nodes"},
            {"name": "Legacy Campus", "role": "Original Samsung fab"}
        ]
    },
    {
        "name": "SAMSUNG AUSTIN", "city": "Austin, TX", "sector": "Semiconductor Foundry",
        "lat": 30.2672, "lng": -97.7431, "marker_color": "#b07cfc", "is_featured": 1,
        "tech_stack": [
            {"name": "14nm FinFET", "role": "US logic node"},
            {"name": "Foundry Lines", "role": "Logic production"},
            {"name": "EUV Lithography", "role": "Node scaling"},
            {"name": "US Operations", "role": "Texas campus"}
        ]
    },
    {
        "name": "SK HYNIX CHEONGJU", "city": "Cheongju, South Korea", "sector": "Memory Manufacturing",
        "lat": 36.6424, "lng": 127.4890, "marker_color": "#fca5a5", "is_featured": 1,
        "tech_stack": [
            {"name": "HBM4", "role": "High-bandwidth memory"},
            {"name": "M11-M16", "role": "Memory fabs"},
            {"name": "238-Layer NAND", "role": "3D NAND"},
            {"name": "EUV Lithography", "role": "Memory scaling"}
        ]
    },
    {
        "name": "SK HYNIX YONGIN", "city": "Yongin, South Korea", "sector": "Memory Manufacturing",
        "lat": 37.2414, "lng": 127.1777, "marker_color": "#fb923c", "is_featured": 1,
        "tech_stack": [
            {"name": "Yongin Cluster", "role": "Next-gen memory"},
            {"name": "HBM4", "role": "AI accelerator memory"},
            {"name": "4 Fabs", "role": "Major expansion"},
            {"name": "EUV Lithography", "role": "Memory scaling"}
        ]
    },
    {
        "name": "MICRON MANASSAS", "city": "Manassas, VA", "sector": "Memory Manufacturing",
        "lat": 38.7509, "lng": -77.4753, "marker_color": "#fde047", "is_featured": 1,
        "tech_stack": [
            {"name": "1α DRAM", "role": "Memory production"},
            {"name": "US Military", "role": "Trusted foundry"},
            {"name": "Specialty Memory", "role": "Rad-hardened chips"},
            {"name": "EUV", "role": "Node scaling"}
        ]
    },
    {
        "name": "MICRON SINGAPORE", "city": "Singapore", "sector": "Memory Manufacturing",
        "lat": 1.3521, "lng": 103.8198, "marker_color": "#facc15", "is_featured": 1,
        "tech_stack": [
            {"name": "HBM3E", "role": "High-bandwidth memory"},
            {"name": "1β DRAM", "role": "Advanced DRAM"},
            {"name": "NAND Assembly", "role": "Packaging hub"},
            {"name": "Fab 10", "role": "Major Singapore fab"}
        ]
    },
    {
        "name": "UMC FAB 12A", "city": "Hsinchu, Taiwan", "sector": "Semiconductor Foundry",
        "lat": 24.8138, "lng": 120.9674, "marker_color": "#34d399", "is_featured": 1,
        "tech_stack": [
            {"name": "28nm", "role": "Specialty logic node"},
            {"name": "Specialty Process", "role": "RF/power/CMOS"},
            {"name": "Foundry Services", "role": "Mature nodes"},
            {"name": "Taiwan Hub", "role": "Hsinchu campus"}
        ]
    },
    {
        "name": "INTEL ARIZONA FAB 52", "city": "Chandler, AZ", "sector": "Semiconductor Foundry",
        "lat": 33.3062, "lng": -111.8407, "marker_color": "#34d399", "is_featured": 1,
        "tech_stack": [
            {"name": "Intel 18A", "role": "1.8nm RibbonFET node"},
            {"name": "High-NA EUV", "role": "Next-gen lithography"},
            {"name": "Ohio-Chandler Fabs", "role": "US expansion"},
            {"name": "PowerVia", "role": "Backside power"}
        ]
    },
    {
        "name": "INTEL OHIO ONE", "city": "New Albany, OH", "sector": "Semiconductor Foundry",
        "lat": 40.0812, "lng": -82.8088, "marker_color": "#5eead4", "is_featured": 1,
        "tech_stack": [
            {"name": "Intel 18A", "role": "1.8nm node"},
            {"name": "High-NA EUV", "role": "Next-gen lithography"},
            {"name": "$20B Campus", "role": "Largest US fab investment"},
            {"name": "RibbonFET", "role": "Gate-all-around"}
        ]
    },
    {
        "name": "GLOBALFOUNDRIES SINGAPORE", "city": "Singapore", "sector": "Semiconductor Foundry",
        "lat": 1.3521, "lng": 103.8198, "marker_color": "#86efac", "is_featured": 1,
        "tech_stack": [
            {"name": "RF SOI", "role": "5G/mmWave RF"},
            {"name": "BCD", "role": "Power management ICs"},
            {"name": "Fab 3", "role": "Singapore production"},
            {"name": "12LP", "role": "FinFET node"}
        ]
    },
    {
        "name": "ST MICROELECTRONICS CROLLES", "city": "Crolles, France", "sector": "Semiconductor Foundry",
        "lat": 45.2815, "lng": 5.8894, "marker_color": "#fbbf24", "is_featured": 1,
        "tech_stack": [
            {"name": "FD-SOI", "role": "Fully-depleted SOI"},
            {"name": "28nm", "role": "Advanced node"},
            {"name": "EU Chips Act", "role": "European fab"},
            {"name": "Automotive MCU", "role": "Power/analog"}
        ]
    },
    {
        "name": "TEXAS INSTRUMENTS RICHARDSON", "city": "Richardson, TX", "sector": "Analog Semiconductor Fab",
        "lat": 32.9483, "lng": -96.7299, "marker_color": "#fbbf24", "is_featured": 1,
        "tech_stack": [
            {"name": "RFAB", "role": "300mm analog fab"},
            {"name": "BCD Power", "role": "Power management"},
            {"name": "Analog Nodes", "role": "45nm analog"},
            {"name": "US Production", "role": "Texas campus"}
        ]
    },
    {
        "name": "IBM ALBANY NANOTECH", "city": "Albany, NY", "sector": "Semiconductor Foundry",
        "lat": 42.6862, "lng": -73.8240, "marker_color": "#818cf8", "is_featured": 1,
        "tech_stack": [
            {"name": "2nm GAA", "role": "Next-gen node"},
            {"name": "R&D Center", "role": "NanoTech complex"},
            {"name": "IBM Research", "role": "Chip innovation"},
            {"name": "US Consortium", "role": "NY center"}
        ]
    },

    # ····· Foundries & Fabs — additional WAICO (China) ·····
    {
        "name": "SMIC BEIJING", "city": "Beijing", "sector": "Semiconductor Foundry",
        "lat": 39.9042, "lng": 116.4074, "marker_color": "#f87171", "is_featured": 1,
        "tech_stack": [
            {"name": "Fab 4", "role": "Beijing production"},
            {"name": "28nm", "role": "Advanced logic node"},
            {"name": "Domestic Tooling", "role": "China supply chain"},
            {"name": "Foundry Services", "role": "Mature nodes"}
        ]
    },
    {
        "name": "SMIC SHANGHAI", "city": "Shanghai", "sector": "Semiconductor Foundry",
        "lat": 31.2304, "lng": 121.4737, "marker_color": "#fca5a5", "is_featured": 1,
        "tech_stack": [
            {"name": "Fabs 1/2/3", "role": "Shanghai production"},
            {"name": "14nm FinFET", "role": "China's leading node"},
            {"name": "Domestic Tooling", "role": "Supply chain independence"},
            {"name": "Foundry Services", "role": "Logic production"}
        ]
    },
    {
        "name": "SMIC SHENZHEN", "city": "Shenzhen, Guangdong", "sector": "Semiconductor Foundry",
        "lat": 22.5431, "lng": 114.0579, "marker_color": "#f87171", "is_featured": 1,
        "tech_stack": [
            {"name": "Fabs 15/16", "role": "Shenzhen production"},
            {"name": "28nm", "role": "Advanced logic node"},
            {"name": "Domestic Tooling", "role": "Supply chain"},
            {"name": "Foundry Services", "role": "Logic production"}
        ]
    },
    {
        "name": "SMIC TIANJIN", "city": "Tianjin", "sector": "Semiconductor Foundry",
        "lat": 39.3434, "lng": 117.3616, "marker_color": "#fca5a5", "is_featured": 1,
        "tech_stack": [
            {"name": "Fabs 7/8/9", "role": "Tianjin production"},
            {"name": "28nm", "role": "Advanced logic node"},
            {"name": "Domestic Tooling", "role": "Supply chain"},
            {"name": "Foundry Services", "role": "Logic production"}
        ]
    },
    {
        "name": "YMTC WUHAN", "city": "Wuhan, Hubei", "sector": "Memory Manufacturing",
        "lat": 30.5928, "lng": 114.3055, "marker_color": "#fbbf24", "is_featured": 1,
        "tech_stack": [
            {"name": "X-tacking", "role": "3D NAND architecture"},
            {"name": "232-Layer NAND", "role": "High-density flash"},
            {"name": "1TB TLC", "role": "Consumer SSD"},
            {"name": "Domestic Tooling", "role": "Supply chain"}
        ]
    },
    {
        "name": "CXMT HEFEI", "city": "Hefei, Anhui", "sector": "Memory Manufacturing",
        "lat": 31.8206, "lng": 117.2272, "marker_color": "#fde047", "is_featured": 1,
        "tech_stack": [
            {"name": "DRAM", "role": "Domestic memory"},
            {"name": "17nm DRAM", "role": "Advanced node"},
            {"name": "Domestic Tooling", "role": "Supply chain"},
            {"name": "HBM Push", "role": "AI memory"}
        ]
    },
    {
        "name": "HUA HONG SHANGHAI", "city": "Shanghai", "sector": "Semiconductor Foundry",
        "lat": 31.2304, "lng": 121.4737, "marker_color": "#fca5a5", "is_featured": 1,
        "tech_stack": [
            {"name": "Specialty Process", "role": "Logic/mixed-signal"},
            {"name": "28nm", "role": "Advanced node"},
            {"name": "Foundry Services", "role": "Mature nodes"},
            {"name": "Domestic Tooling", "role": "Supply chain"}
        ]
    },
    {
        "name": "HUA HONG WUXI", "city": "Wuxi, Jiangsu", "sector": "Semiconductor Foundry",
        "lat": 31.4912, "lng": 120.3119, "marker_color": "#f87171", "is_featured": 1,
        "tech_stack": [
            {"name": "Specialty Process", "role": "Logic/mixed-signal"},
            {"name": "Foundry Services", "role": "Mature nodes"},
            {"name": "Automotive IC", "role": "Power/analog"},
            {"name": "Domestic Tooling", "role": "Supply chain"}
        ]
    },

    # ····· Special / Sovereign / National (WAICO China hubs) ·····
    {
        "name": "CHINA TELECOM HOHHOT", "city": "Hohhot, Inner Mongolia", "sector": "Cloud Region / Sovereign Cloud",
        "lat": 40.8426, "lng": 111.7492, "marker_color": "#f87171", "is_featured": 1,
        "tech_stack": [
            {"name": "National Hub", "role": "Inner Mongolia hub"},
            {"name": "Cool Climate", "role": "High-altitude cooling"},
            {"name": "Sovereign Cloud", "role": "State data platform"},
            {"name": "Wind Power", "role": "Renewable PPA"}
        ]
    },
    {
        "name": "CHINA MOBILE BEIJING", "city": "Beijing", "sector": "Cloud Region / Sovereign Cloud",
        "lat": 39.9042, "lng": 116.4074, "marker_color": "#fca5a5", "is_featured": 1,
        "tech_stack": [
            {"name": "Mobile Cloud", "role": "State cloud platform"},
            {"name": "National Hub", "role": "Beijing hub"},
            {"name": "Sovereign Cloud", "role": "State data platform"},
            {"name": "5G Edge", "role": "Edge compute"}
        ]
    },
    {
        "name": "CHINA UNICOM HOHHOT", "city": "Hohhot, Inner Mongolia", "sector": "Cloud Region / Sovereign Cloud",
        "lat": 40.8426, "lng": 111.7492, "marker_color": "#f87171", "is_featured": 1,
        "tech_stack": [
            {"name": "National Hub", "role": "Inner Mongolia hub"},
            {"name": "Sovereign Cloud", "role": "State data platform"},
            {"name": "Cool Climate", "role": "High-altitude cooling"},
            {"name": "Wind Power", "role": "Renewable PPA"}
        ]
    },
    {
        "name": "CHINA NATIONAL GANSU HUB", "city": "Lanzhou, Gansu", "sector": "Cloud Region / Sovereign Cloud",
        "lat": 36.0611, "lng": 103.8343, "marker_color": "#fca5a5", "is_featured": 1,
        "tech_stack": [
            {"name": "National Hub", "role": "Gansu computing hub"},
            {"name": "Cool Climate", "role": "High-altitude cooling"},
            {"name": "Sovereign Cloud", "role": "State data platform"},
            {"name": "Solar Power", "role": "Renewable PPA"}
        ]
    },
    {
        "name": "CHINA NATIONAL NINGXIA HUB", "city": "Zhongwei, Ningxia", "sector": "Cloud Region / Sovereign Cloud",
        "lat": 37.5059, "lng": 105.1889, "marker_color": "#f87171", "is_featured": 1,
        "tech_stack": [
            {"name": "National Hub", "role": "Ningxia computing hub"},
            {"name": "Cool Climate", "role": "High-altitude cooling"},
            {"name": "Sovereign Cloud", "role": "State data platform"},
            {"name": "Solar Power", "role": "Renewable PPA"}
        ]
    },
    {
        "name": "ORACLE OCI OAXACA", "city": "Oaxaca, Mexico", "sector": "Cloud Region / Sovereign Cloud",
        "lat": 17.0732, "lng": -96.7266, "marker_color": "#2dd4bf", "is_featured": 1,
        "tech_stack": [
            {"name": "OCI", "role": "Oracle Cloud Infrastructure"},
            {"name": "Autonomous Database", "role": "Self-driving DB"},
            {"name": "Exadata", "role": "Database machine"},
            {"name": "Sovereign Zone", "role": "Latin data residency"}
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
