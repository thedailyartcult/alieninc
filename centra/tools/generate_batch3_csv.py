"""Generate 230+ new plugin definitions CSV — batch 3 of real CVEs & discovery."""
import csv
from pathlib import Path


def make_rows():
    rows = []
    pid = 2108

    # ── Batch 1: Real CVEs from CISA KEV 2026 (80, IDs 2108-2187) ──
    cves = [
        # SonicWall
        ("SonicWall SMA1000 Unauthenticated SSRF to RCE (CVE-2026-15409)", "SonicWall SMA1000 contains unauthenticated SSRF chained with admin code injection allowing full appliance takeover.", 10.0, "Critical", "Network Devices", "/sma/", "CVE-2026-15409"),
        # Adobe ColdFusion
        ("Adobe ColdFusion RDS Path Traversal RCE (CVE-2026-48282)", "Adobe ColdFusion RDS FILEIO path traversal allows unauthenticated remote code execution.", 10.0, "Critical", "Web Application", "/cfide/", "CVE-2026-48282"),
        # Fortinet FortiSandbox
        ("Fortinet FortiSandbox Command Injection VNC (CVE-2026-25089)", "Unauthenticated command injection in FortiSandbox via Start VNC feature.", 9.8, "Critical", "Network Devices", "/fortisandbox/", "CVE-2026-25089"),
        ("Fortinet FortiSandbox Root Command Injection (CVE-2026-39808)", "Unauthenticated root command injection in FortiSandbox via tracer-behavior API.", 9.8, "Critical", "Network Devices", "/fortisandbox/", "CVE-2026-39808"),
        # Microsoft SharePoint
        ("Microsoft SharePoint Server Deserialization RCE (CVE-2026-58644)", "Unauthenticated RCE in SharePoint Server via deserialization of untrusted data.", 9.8, "Critical", "Web Application", "/_layouts/", "CVE-2026-58644"),
        # Oracle E-Business Suite
        ("Oracle E-Business Suite Unauthenticated PE (CVE-2026-46817)", "Unauthenticated privilege escalation in Oracle EBS via ibytransmit endpoint.", 9.8, "Critical", "Web Application", "/oracle/", "CVE-2026-46817"),
        # SimpleHelp RMM
        ("SimpleHelp RMM OIDC Token Forgery (CVE-2026-48558)", "Unauthenticated OIDC token forgery in SimpleHelp RMM bypassing authentication and MFA.", 10.0, "Critical", "Web Application", "/simplehelp/", "CVE-2026-48558"),
        # Ubiquiti UniFi
        ("Ubiquiti UniFi OS Auth Bypass (CVE-2026-34908)", "Authentication bypass in UniFi OS via URI normalization mismatch allows unauthorized changes.", 10.0, "Critical", "Network Devices", "/unifi/", "CVE-2026-34908"),
        ("Ubiquiti UniFi OS Path Traversal Key Exfil (CVE-2026-34909)", "Path traversal in UniFi OS enables signing key exfiltration for auth bypass.", 10.0, "Critical", "Network Devices", "/unifi/", "CVE-2026-34909"),
        ("Ubiquiti UniFi OS Command Injection RCE (CVE-2026-34910)", "Command injection at package update endpoint in UniFi OS gives unauthenticated root RCE.", 10.0, "Critical", "Network Devices", "/unifi/", "CVE-2026-34910"),
        # Ivanti Sentry
        ("Ivanti Sentry Pre-Auth OS Command Injection (CVE-2026-10520)", "Pre-authentication OS command injection via unauthenticated MICS configuration endpoint in Ivanti Sentry.", 10.0, "Critical", "Network Devices", "/sentry/", "CVE-2026-10520"),
        # PTC Windchill
        ("PTC Windchill Pre-Auth Deserialization RCE (CVE-2026-12569)", "Unauthenticated pre-auth RCE via deserialization in PTC Windchill/FlexPLM.", 9.8, "Critical", "Web Application", "/windchill/", "CVE-2026-12569"),
        # Splunk Enterprise
        ("Splunk Enterprise PostgreSQL Sidecar RCE (CVE-2026-20253)", "Unauthenticated RCE in Splunk Enterprise via PostgreSQL sidecar service.", 9.8, "Critical", "Web Application", "/splunk/", "CVE-2026-20253"),
        # Joomla
        ("Joomla Content Editor PHP Upload RCE (CVE-2026-48907)", "Unauthenticated PHP file upload RCE in Joomla Content Editor via profile import.", 9.8, "Critical", "Web Application", "/joomla/", "CVE-2026-48907"),
        ("iCagenda Frontend Upload RCE (CVE-2026-48939)", "Frontend attachment upload zero-day in iCagenda exploited hours before patch.", 9.8, "Critical", "Web Application", "/icagenda/", "CVE-2026-48939"),
        ("JoomShaper SP Page Builder Shell Upload (CVE-2026-48908)", "Unauthenticated uploadCustomIcon in JoomShaper SP Page Builder enables PHP web shell upload.", 9.8, "Critical", "Web Application", "/sp-page-builder/", "CVE-2026-48908"),
        ("Joomlack Page Builder CK Upload Bypass (CVE-2026-56290)", "CSRF-token-only upload check bypass via public token harvesting in Joomlack Page Builder CK.", 9.8, "Critical", "Web Application", "/pagebuilderck/", "CVE-2026-56290"),
        ("Balbooa Forms Attachment Upload RCE (CVE-2026-56291)", "Attachment upload extension re-attached verbatim in Balbooa Forms, exploited as zero-day.", 9.8, "Critical", "Web Application", "/balbooa/", "CVE-2026-56291"),
        # Oracle PeopleSoft
        ("Oracle PeopleSoft Pre-Auth SSRF RCE (CVE-2026-35273)", "Pre-authentication SSRF/RCE in Oracle PeopleSoft Enterprise PeopleTools Updates Environment Management.", 9.8, "Critical", "Web Application", "/peoplesoft/", "CVE-2026-35273"),
        ("Oracle PeopleSoft Performance Monitor RCE (CVE-2026-35278)", "Pre-authentication RCE in Oracle PeopleSoft PeopleTools Performance Monitor, chained with CVE-2026-35273.", 9.8, "Critical", "Web Application", "/peoplesoft/", "CVE-2026-35278"),
        # Mirasvit
        ("Mirasvit Full Page Cache Warmer RCE (CVE-2026-45247)", "PHP object injection in Mirasvit FPC Warmer for Magento allows unauthenticated RCE.", 9.8, "Critical", "Web Application", "/fpcwarmer/", "CVE-2026-45247"),
        # Check Point
        ("Check Point Security Gateway IKEv1 Bypass (CVE-2026-50751)", "IKEv1 auth bypass in Check Point Security Gateway allows unauthenticated VPN access exploited by Qilin ransomware.", 9.3, "Critical", "Network Devices", "/checkpoint/", "CVE-2026-50751"),
        # Cisco SD-WAN
        ("Cisco Catalyst SD-WAN Auth Bypass (CVE-2026-20182)", "Unauthenticated remote auth bypass in Cisco Catalyst SD-WAN via vdaemon DTLS vHub confusion.", 10.0, "Critical", "Network Devices", "/sdwan/", "CVE-2026-20182"),
        ("Cisco SD-WAN Peering Auth Bypass (CVE-2026-20127)", "CVSS 10.0 peering authentication bypass in Cisco Catalyst SD-WAN enabling fabric-wide NETCONF access.", 10.0, "Critical", "Network Devices", "/sdwan/", "CVE-2026-20127"),
        # LiteLLM
        ("BerriAI LiteLLM Pre-Auth SQL Injection (CVE-2026-42208)", "Pre-authentication SQL injection via unsanitized Bearer token in BerriAI LiteLLM.", 9.8, "Critical", "Web Application", "/litellm/", "CVE-2026-42208"),
        ("BerriAI LiteLLM MCP Command Injection (CVE-2026-42271)", "MCP test endpoint command injection chains with Starlette auth bypass for unauthenticated RCE.", 8.8, "High", "Web Application", "/litellm/", "CVE-2026-42271"),
        # Supply Chain
        ("Nx Console Supply Chain Credential Stealer (CVE-2026-48027)", "Supply-chain credential stealer via TanStack-linked developer compromise in Nx Console VS Code extension.", 9.8, "Critical", "Web Application", "/", "CVE-2026-48027"),
        ("TanStack Supply-Chain Worm (CVE-2026-45321)", "Self-propagating supply-chain worm via GitHub Actions cache poisoning and OIDC token extraction.", 9.6, "Critical", "Web Application", "/", "CVE-2026-45321"),
        # LiteSpeed
        ("LiteSpeed cPanel Plugin Root RCE (CVE-2026-48172)", "Any cPanel user can execute arbitrary scripts as root via unguarded lsws.redisAble API endpoint.", 9.8, "Critical", "Web Application", "/litespeed/", "CVE-2026-48172"),
        # PAN-OS
        ("Palo Alto PAN-OS Auth Portal RCE (CVE-2026-0300)", "Unauthenticated RCE via out-of-bounds write in PAN-OS authentication portal.", 9.3, "Critical", "Network Devices", "/global-protect/", "CVE-2026-0300"),
        # cPanel
        ("WebPros cPanel WHM CRLF Injection (CVE-2026-41940)", "Pre-authentication CRLF injection in cPanel WHM grants unauthenticated root WHM access.", 9.8, "Critical", "Web Application", "/whm/", "CVE-2026-41940"),
        # Marimo
        ("Marimo Pre-Auth RCE WebSocket (CVE-2026-39987)", "Pre-authentication RCE via unauthenticated terminal WebSocket in Marimo.", 9.8, "Critical", "Web Application", "/marimo/", "CVE-2026-39987"),
        # Fortinet
        ("Fortinet FortiClient EMS SQL Injection (CVE-2026-21643)", "Pre-authentication SQL injection in FortiClient EMS via Site HTTP header.", 9.8, "Critical", "Network Devices", "/forticlient/", "CVE-2026-21643"),
        ("Fortinet FortiClient EMS Pre-Auth RCE (CVE-2026-35616)", "Pre-authentication RCE in Fortinet FortiClient EMS.", 9.8, "Critical", "Network Devices", "/forticlient/", "CVE-2026-35616"),
        ("Fortinet FortiCloud SSO Auth Bypass (CVE-2026-24858)", "Cross-tenant authentication bypass in Fortinet FortiCloud SSO lets attackers log into other customers' devices.", 9.8, "Critical", "Network Devices", "/forticloud/", "CVE-2026-24858"),
        # Ivanti EPMM
        ("Ivanti EPMM Pre-Auth RCE URL Injection (CVE-2026-1340)", "Pre-authentication RCE in Ivanti EPMM via Android File Transfer URL injection.", 9.8, "Critical", "Web Application", "/epmm/", "CVE-2026-1340"),
        ("Ivanti EPMM Pre-Auth RCE Bash Injection (CVE-2026-1281)", "Pre-authentication RCE in Ivanti EPMM via App Store URL bash injection.", 9.8, "Critical", "Web Application", "/epmm/", "CVE-2026-1281"),
        # Cisco FMC
        ("Cisco Secure FMC Java Deserialization RCE (CVE-2026-20131)", "Unauthenticated RCE in Cisco Secure Firewall Management Center via Java deserialization.", 10.0, "Critical", "Network Devices", "/fmc/", "CVE-2026-20131"),
        # Citrix
        ("Citrix NetScaler ADC SAML Memory Overread (CVE-2026-3055)", "Memory overread via insufficient input validation in Citrix NetScaler ADC SAML IDP.", 9.8, "Critical", "Network Devices", "/netscaler/", "CVE-2026-3055"),
        # Langflow
        ("Langflow Public Flow Build RCE (CVE-2026-33017)", "Unauthenticated RCE in Langflow via public flow build endpoint.", 9.8, "Critical", "Web Application", "/langflow/", "CVE-2026-33017"),
        ("Langflow Flow-ID Bypass API Key Exfil (CVE-2026-55255)", "Flow-ID ownership check bypass in Langflow /responses endpoint used to exfiltrate API keys.", 8.4, "High", "Web Application", "/langflow/", "CVE-2026-55255"),
        # Dell
        ("Dell RP4VMs Hardcoded Credentials Root RCE (CVE-2026-22769)", "Hardcoded Tomcat admin credentials in Dell RP4VMs allow unauthenticated root access exploited by PRC-nexus UNC6201.", 10.0, "Critical", "Web Application", "/rp4vms/", "CVE-2026-22769"),
        # SmarterMail
        ("SmarterMail ConnectToHub OS Command Exec (CVE-2026-24423)", "Unauthenticated ConnectToHub API enables OS command execution via malicious server redirect.", 9.8, "Critical", "Web Application", "/smartemail/", "CVE-2026-24423"),
        ("SmarterMail Admin Password Reset Bypass (CVE-2026-23760)", "Unauthenticated admin password reset via IsSysAdmin bypass exploited within 2 days of patch.", 9.8, "Critical", "Web Application", "/smartemail/", "CVE-2026-23760"),
        # GNU InetUtils
        ("GNU InetUtils telnetd USER Variable Root Shell (CVE-2026-24061)", "11-year-old USER variable injection in GNU InetUtils telnetd grants instant unauthenticated root shell.", 9.8, "Critical", "Network Devices", "/", "CVE-2026-24061"),
        # Microsoft High CVEs
        ("Microsoft AD FS DKM LPE (CVE-2026-56155)", "Local privilege escalation in Microsoft AD FS Distributed Key Manager discovered during active intrusion response.", 7.8, "High", "Windows", "/", "CVE-2026-56155"),
        ("Microsoft Exchange OWA Stored XSS (CVE-2026-42897)", "Stored XSS in Microsoft Exchange Server OWA via crafted email enables session hijacking.", 8.1, "High", "Web Application", "/owa/", "CVE-2026-42897"),
        ("Microsoft Defender Symlink LPE (CVE-2026-41091)", "Low-privilege symlink following in Microsoft Defender escalates to SYSTEM linked to BlueHammer chain.", 7.8, "High", "Windows", "/", "CVE-2026-41091"),
        ("Microsoft Defender BlueHammer TOCTOU (CVE-2026-33825)", "BlueHammer TOCTOU race condition in Microsoft Defender enables LPE to SYSTEM.", 7.8, "High", "Windows", "/", "CVE-2026-33825"),
        ("Microsoft Defender Antimalware Crash (CVE-2026-45498)", "Crafted payload crashes Microsoft Defender scan engine creating detection blind spot.", 4.0, "Medium", "Windows", "/", "CVE-2026-45498"),
        ("Microsoft Windows Shell SmartScreen Bypass LNK (CVE-2026-21510)", "SmartScreen bypass via malicious LNK files delivered over the network.", 8.8, "High", "Windows", "/", "CVE-2026-21510"),
        ("Microsoft MSHTML MotW Bypass LNK (CVE-2026-21513)", "Mark-of-the-Web bypass in MSHTML exploited by APT28 via malicious LNK files.", 8.8, "High", "Windows", "/", "CVE-2026-21513"),
        ("Microsoft Office Word OLE Security Bypass (CVE-2026-21514)", "OLE security bypass in Microsoft Office Word exploited by MuddyWater.", 7.8, "High", "Windows", "/", "CVE-2026-21514"),
        ("Microsoft Windows DWM Type Confusion LPE (CVE-2026-21519)", "Type confusion in Windows DWM enables local privilege escalation to SYSTEM.", 7.8, "High", "Windows", "/", "CVE-2026-21519"),
        ("Microsoft Windows RDS TermService LPE (CVE-2026-21533)", "TermService registry LPE in Windows Remote Desktop Services.", 7.8, "High", "Windows", "/", "CVE-2026-21533"),
        ("Microsoft Office OLE Bypass APT28 (CVE-2026-21509)", "OLE security feature bypass in Microsoft Office exploited by APT28.", 7.8, "High", "Windows", "/", "CVE-2026-21509"),
        ("Microsoft Windows RasMan DoS (CVE-2026-21525)", "NULL pointer dereference in Remote Access Connection Manager enabling local DoS.", 6.2, "Medium", "Windows", "/", "CVE-2026-21525"),
        ("Microsoft Windows DWM ALPC Address Leak (CVE-2026-20805)", "ASLR-defeating ALPC section address leak in Windows DWM.", 5.5, "Medium", "Windows", "/", "CVE-2026-20805"),
        # Google
        ("Google Chrome V8 Zero-Day OOB RCE (CVE-2026-11645)", "Fifth 2026 V8 zero-day in Google Chrome, TurboFan JIT OOB enables in-sandbox RCE.", 8.8, "High", "Web Application", "/", "CVE-2026-11645"),
        ("Google Dawn Use-After-Free (CVE-2026-5281)", "Use-after-free vulnerability in Google Dawn graphics rendering.", 8.8, "High", "Web Application", "/", "CVE-2026-5281"),
        ("Google Skia OOB Write (CVE-2026-3909)", "Out-of-bounds write in Google Skia via crafted HTML page.", 8.8, "High", "Web Application", "/", "CVE-2026-3909"),
        ("Google Chromium V8 ACE (CVE-2026-3910)", "Arbitrary code execution in Google Chromium V8 via inappropriate implementation.", 8.8, "High", "Web Application", "/", "CVE-2026-3910"),
        ("Google Chrome CSS Use-After-Free (CVE-2026-2441)", "CSS use-after-free in Google Chrome/Chromium enabling renderer code execution.", 8.8, "High", "Web Application", "/", "CVE-2026-2441"),
        # Cisco
        ("Cisco Unified CM SSRF WebDialer (CVE-2026-20230)", "Unauthenticated SSRF in Cisco Unified CM via WebDialer enabling file write and root escalation.", 8.6, "High", "Network Devices", "/unifiedcm/", "CVE-2026-20230"),
        ("Cisco SD-WAN Manager Local CLI RCE (CVE-2026-20245)", "Authenticated local CLI input escaping in Cisco Catalyst SD-WAN Manager allows root command execution.", 7.8, "High", "Network Devices", "/sdwan/", "CVE-2026-20245"),
        ("Cisco SD-WAN Manager Path Traversal (CVE-2026-20262)", "Arbitrary file write via path traversal in Cisco Catalyst SD-WAN Manager leading to root.", 6.5, "Medium", "Network Devices", "/sdwan/", "CVE-2026-20262"),
        ("Cisco SD-WAN DCA Credential Exposure (CVE-2026-20128)", "DCA credential exposure via accessible filesystem in Cisco SD-WAN Manager enabling PE.", 7.5, "High", "Network Devices", "/sdwan/", "CVE-2026-20128"),
        ("Cisco SD-WAN API Info Disclosure (CVE-2026-20133)", "Unauthenticated API information disclosure as first step in SD-WAN attack chain.", 6.5, "Medium", "Network Devices", "/sdwan/", "CVE-2026-20133"),
        ("Cisco SD-WAN API File Overwrite (CVE-2026-20122)", "Authenticated API file overwrite enabling vManage privilege escalation.", 5.4, "Medium", "Network Devices", "/sdwan/", "CVE-2026-20122"),
        ("Cisco Unified CM Pre-Auth RCE (CVE-2026-20045)", "Pre-authentication RCE in Cisco Unified Communications Manager via HTTP request injection.", 8.2, "High", "Network Devices", "/unifiedcm/", "CVE-2026-20045"),
        # SolarWinds
        ("SolarWinds Serv-U DoS (CVE-2026-28318)", "Unauthenticated deflate header DoS crashes file transfer service in SolarWinds Serv-U.", 7.5, "High", "Web Application", "/serv-u/", "CVE-2026-28318"),
        # Adobe
        ("Adobe Acrobat JavaScript Prototype Pollution (CVE-2026-34621)", "Zero-day JavaScript prototype pollution in Adobe Acrobat Reader leading to arbitrary code execution.", 8.6, "High", "Web Application", "/", "CVE-2026-34621"),
        # Apache
        ("Apache ActiveMQ Classic Jolokia RCE (CVE-2026-34197)", "Authenticated RCE via Jolokia JMX-HTTP bridge in Apache ActiveMQ Classic (13-year-old flaw).", 8.8, "High", "Web Servers", "/activemq/", "CVE-2026-34197"),
        # Trivy
        ("Aquasecurity Trivy Supply Chain Compromise (CVE-2026-33634)", "Supply chain compromise in Aquasecurity Trivy via embedded malicious code.", 8.8, "High", "Container Security", "/", "CVE-2026-33634"),
        # Ivanti
        ("Ivanti EPM Unauthenticated Credential Vault Access (CVE-2026-1603)", "Unauthenticated credential vault access in Ivanti EPM via magic number header bypass.", 8.6, "High", "Web Application", "/epm/", "CVE-2026-1603"),
        ("Ivanti EPMM Authenticated Admin RCE (CVE-2026-6973)", "Authenticated admin RCE in Ivanti EPMM chained from CVE-2026-1340 credential theft.", 7.2, "High", "Web Application", "/epmm/", "CVE-2026-6973"),
        # VMware
        ("Broadcom VMware Aria Pre-Auth Command Injection (CVE-2026-22719)", "Pre-auth command injection in VMware Aria Operations during support-assisted migration workflow.", 8.1, "High", "Web Application", "/aria/", "CVE-2026-22719"),
        # Qualcomm
        ("Qualcomm Multiple Chipsets Memory Corruption (CVE-2026-21385)", "Memory corruption via integer overflow in memory allocation across Qualcomm chipsets.", 7.8, "High", "Network Devices", "/", "CVE-2026-21385"),
        # Soliton
        ("Soliton FileZen OS Command Injection (CVE-2026-25108)", "Authenticated OS command injection in Soliton FileZen via antivirus check handler.", 8.8, "High", "Web Application", "/filezen/", "CVE-2026-25108"),
        # Apple
        ("Apple dyld Memory Corruption (CVE-2026-20700)", "Memory corruption in Apple dyld dynamic linker enabling code execution in Google TAG spyware chain.", 7.8, "High", "Web Application", "/", "CVE-2026-20700"),
        # SonicWall
        ("SonicWall SMA1000 Authenticated Code Injection (CVE-2026-15410)", "Authenticated code injection in SonicWall SMA1000 chained with SSRF for full takeover.", 7.2, "High", "Network Devices", "/sma/", "CVE-2026-15410"),
        # LiteSpeed
        ("LiteSpeed cPanel Symlink PE (CVE-2026-54420)", "Symlink following privilege escalation in LiteSpeed cPanel plugin on shared hosting.", 8.5, "High", "Web Application", "/litespeed/", "CVE-2026-54420"),
        # TrueConf
        ("TrueConf Client Insecure Update RCE (CVE-2026-3502)", "Arbitrary code execution in TrueConf Client via insecure update mechanism.", 7.8, "High", "Web Application", "/trueconf/", "CVE-2026-3502"),
        # Drupal
        ("Drupal Core SQL Injection PostgreSQL (CVE-2026-9082)", "Unauthenticated SQL injection in Drupal Core via PostgreSQL EntityQuery array key injection.", 6.5, "Medium", "Web Application", "/drupal/", "CVE-2026-9082"),
        # Arista
        ("Arista EOS Tunnel Protocol Confusion (CVE-2026-7473)", "ASIC-level tunnel protocol confusion in Arista EOS enables network segmentation bypass.", 5.8, "Medium", "Network Devices", "/", "CVE-2026-7473"),
        # Trend Micro
        ("Trend Micro Apex One Path Traversal (CVE-2026-34926)", "Local admin path traversal in Trend Micro Apex One overwrites agent key table to inject code.", 6.7, "Medium", "Windows", "/", "CVE-2026-34926"),
        # Microsoft SharePoint Medium
        ("Microsoft SharePoint Unauthenticated Access Primitive (CVE-2026-56164)", "Unauthenticated access primitive in SharePoint chained into IIS machine key theft.", 5.3, "Medium", "Web Application", "/_layouts/", "CVE-2026-56164"),
        ("Microsoft SharePoint Network Spoofing (CVE-2026-32201)", "Network spoofing in Microsoft SharePoint Server via improper input validation.", 6.5, "Medium", "Web Application", "/_layouts/", "CVE-2026-32201"),
        ("Microsoft Windows Shell NTLM Credential Coercion (CVE-2026-32202)", "NTLM credential coercion via malicious LNK files in Windows Shell.", 4.3, "Medium", "Windows", "/", "CVE-2026-32202"),
        # Oracle CPU July 2026
        ("Oracle WebLogic Server T3 IIOP RCE (CVE-2026-35263)", "Critical RCE in Oracle WebLogic Server via T3/IIOP protocol.", 9.9, "Critical", "Web Application", "/weblogic/", "CVE-2026-35263"),
        ("Oracle Identity Manager HTTP RCE (CVE-2026-35268)", "Remote code execution in Oracle Identity Manager via HTTP.", 9.9, "Critical", "Web Application", "/oim/", "CVE-2026-35268"),
        ("Oracle WebCenter Sites RCE (CVE-2026-35270)", "Remote code execution in Oracle WebCenter Sites.", 9.1, "Critical", "Web Application", "/webcenter/", "CVE-2026-35270"),
        ("Oracle WebCenter Capture RCE (CVE-2026-35280)", "Remote code execution in Oracle WebCenter Capture.", 9.9, "Critical", "Web Application", "/webcenter/", "CVE-2026-35280"),
        ("Oracle WebCenter Capture RCE 2 (CVE-2026-35281)", "Additional remote code execution in Oracle WebCenter Capture.", 9.9, "Critical", "Web Application", "/webcenter/", "CVE-2026-35281"),
        # Jenkins
        ("Jenkins Deserialization RCE (CVE-2026-53435)", "Attackers can deserialize arbitrary types from config.xml submission in Jenkins allowing RCE.", 9.8, "Critical", "Web Application", "/jenkins/", "CVE-2026-53435"),
        # Apache Tomcat
        ("Apache Tomcat EncryptInterceptor RCE (CVE-2026-29146)", "Padding oracle vulnerability in Apache Tomcat EncryptInterceptor allows cluster message forgery and RCE.", 9.1, "Critical", "Web Servers", "/", "CVE-2026-29146"),
        # Ivanti 2025
        ("Ivanti Connect Secure Stack Overflow RCE (CVE-2025-0282)", "Stack-based buffer overflow in Ivanti Connect Secure pre-authentication RCE exploited by Chinese APT.", 9.0, "Critical", "Network Devices", "/dana-na/", "CVE-2025-0282"),
        # Linux Kernel
        ("Linux Kernel Copy Fail LPE (CVE-2026-31431)", "Linux kernel algif_aead page cache write for local privilege escalation.", 7.8, "High", "Network Devices", "/", "CVE-2026-31431"),
    ]
    for name, desc, cvss, sev, fam, path, cve in cves:
        rows.append({
            "name": name, "description": desc[:200],
            "solution": f"Apply vendor patch for {cve}. Upgrade to latest version.",
            "cvss": str(cvss), "severity": sev, "family": fam,
            "type": "path", "path": path, "indicator": "",
            "header": "", "ports": "80, 443, 8080, 8443, 3000, 5000, 9000", "cve": cve,
        })

    # ── Batch 2: More Web Paths / Admin Panels (40, IDs 2188-2227) ──
    more_paths = [
        ("Cloudflare CDN Origin IP Detection", "/cdn-cgi/trace", 4.0, "Medium"),
        ("AWS ALB Health Check", "/healthcheck/", 3.0, "Low"),
        ("Google Cloud LB Health", "/healthz/", 3.0, "Low"),
        ("Azure App Service Health", "/robots933456.txt", 3.0, "Low"),
        ("Nginx Status Page", "/nginx_status", 4.0, "Medium"),
        ("Apache Server Status", "/server-status", 4.0, "Medium"),
        ("Apache Server Info", "/server-info", 4.0, "Medium"),
        ("PHP-FPM Status", "/status", 4.0, "Medium"),
        ("PHP-FPM Ping", "/ping", 3.0, "Low"),
        ("Varnish Cache Admin", "/varnish/", 4.0, "Medium"),
        ("Squid Proxy Manager", "/squid/", 4.0, "Medium"),
        ("HAProxy Stats JSON", "/haproxy;json", 4.0, "Medium"),
        ("Nginx Amplify Agent", "/amplify/", 3.0, "Low"),
        ("Datadog Agent", "/agent/", 3.0, "Low"),
        ("New Relic Agent", "/newrelic-agent/", 3.0, "Low"),
        ("OpenTelemetry Collector", "/otel/", 3.0, "Low"),
        ("Jaeger Tracing UI", "/jaeger/", 3.0, "Low"),
        ("Zipkin Tracing UI", "/zipkin/", 3.0, "Low"),
        ("Tempo Tracing", "/tempo/", 3.0, "Low"),
        ("Pyroscope Profiling", "/pyroscope/", 3.0, "Low"),
        ("Grafana Loki Logs", "/loki/", 3.0, "Low"),
        ("Mimir Metrics", "/mimir/", 3.0, "Low"),
        ("Cortex Metrics", "/cortex/", 3.0, "Low"),
        ("Thanos Query", "/thanos/", 3.0, "Low"),
        ("VictoriaMetrics", "/victoria-metrics/", 3.0, "Low"),
        ("ClickHouse HTTP Interface", "/clickhouse/", 5.0, "Medium"),
        ("InfluxDB HTTP API", "/influxdb/", 5.0, "Medium"),
        ("TimescaleDB HTTP", "/timescaledb/", 3.0, "Low"),
        ("CockroachDB HTTP", "/cockroachdb/", 3.0, "Low"),
        ("Neo4j Browser", "/neo4j/", 3.0, "Low"),
        ("ArangoDB Web UI", "/arango/", 3.0, "Low"),
        ("Couchbase Web Console", "/couchbase/", 5.0, "Medium"),
        ("MariaDB HTTP", "/mariadb/", 3.0, "Low"),
        ("Cassandra OpsCenter", "/cassandra/", 3.0, "Low"),
        ("MongoDB Express", "/mongodb-express/", 5.0, "Medium"),
        ("Redis Commander", "/redis-commander/", 5.0, "Medium"),
        ("Adminer Database Manager", "/adminer.php", 8.0, "High"),
        ("PHPMyAdmin", "/phpmyadmin/", 8.0, "High"),
        ("PHPMyAdmin 2", "/phpMyAdmin/", 8.0, "High"),
        ("PHPMyAdmin 3", "/pma/", 8.0, "High"),
    ]
    for name, path, cvss, sev in more_paths:
        rows.append({
            "name": name, "description": f"Detects exposed {name} at {path}",
            "solution": "Restrict access to this endpoint. Use authentication and network segmentation.",
            "cvss": str(cvss), "severity": sev, "family": "Web Security",
            "type": "path", "path": path, "indicator": "", "header": "",
            "ports": "80, 443, 8080, 8443, 3000, 5000, 6443, 9000", "cve": "",
        })

    # ── Batch 3: More Discovery/Config Files (20, IDs 2228-2247) ──
    discovery_files = [
        ("Gatsby Build Info", "/___graphql", 3.0, "Low"),
        ("Next.js Source Maps", "/_next/static/chunks/pages/", 4.0, "Medium"),
        ("Nuxt.js Dev Server", "/_nuxt/", 3.0, "Low"),
        ("Astro Assets", "/_astro/", 3.0, "Low"),
        ("Vite Dev Server", "/@vite/", 3.0, "Low"),
        ("Webpack Bundle Analyzer", "/webpack/", 3.0, "Low"),
        ("Rollup Bundle", "/bundle.js", 3.0, "Low"),
        ("Parcel Bundle", "/parcel/", 3.0, "Low"),
        ("ESBuild Config", "/esbuild/", 3.0, "Low"),
        ("TurboPack Config", "/turbopack/", 3.0, "Low"),
        ("Babel Config", "/babel/", 3.0, "Low"),
        ("SWC Config", "/swc/", 3.0, "Low"),
        ("PostCSS Config", "/postcss.config.js", 3.0, "Low"),
        ("Tailwind Config", "/tailwind.config.js", 3.0, "Low"),
        ("Nginx Config Backup", "/nginx.conf", 5.0, "Medium"),
        ("Apache Config Backup", "/httpd.conf", 5.0, "Medium"),
        ("Env File", "/.env", 9.0, "Critical"),
        ("Env Local File", "/.env.local", 9.0, "Critical"),
        ("Env Prod File", "/.env.production", 9.0, "Critical"),
        ("Docker Compose", "/docker-compose.yml", 7.0, "High"),
    ]
    for name, path, cvss, sev in discovery_files:
        rows.append({
            "name": name, "description": f"Detects {name} at {path}",
            "solution": "Remove or secure this file/endpoint if not needed.",
            "cvss": str(cvss), "severity": sev, "family": "Information Gathering",
            "type": "path", "path": path, "indicator": "", "header": "",
            "ports": "80, 443, 8080, 8443", "cve": "",
        })

    # ── Batch 4: More API Endpoints (30, IDs 2248-2277) ──
    api_endpoints = [
        "/api/v3/", "/api/v4/", "/api/v5/",
        "/api/health", "/api/ready", "/api/live",
        "/api/info", "/api/version", "/api/ping",
        "/api/users", "/api/auth", "/api/token",
        "/api/login", "/api/logout", "/api/register",
        "/api/upload", "/api/download", "/api/export",
        "/api/import", "/api/sync", "/api/backup",
        "/api/restore", "/api/migrate", "/api/audit",
        "/api/logs", "/api/events", "/api/metrics",
        "/api/traces", "/api/profiling", "/api/debug/pprof/cmdline",
    ]
    for path in api_endpoints:
        rows.append({
            "name": f"API Endpoint: {path}",
            "description": f"Detects exposed API endpoint at {path}",
            "solution": "Restrict API endpoint access. Implement authentication if needed.",
            "cvss": "5.0", "severity": "Medium", "family": "API Security",
            "type": "path", "path": path, "indicator": "", "header": "",
            "ports": "80, 443, 8080, 8443, 3000, 5000, 6443", "cve": "",
        })

    # ── Batch 5: More WordPress Plugins (30, IDs 2278-2307) ──
    wp_plugins = [
        "akismet", "contact-form-7", "classic-editor", "elementor",
        "jetpack", "wpforms-lite", "yoast-seo", "wordpress-seo",
        "woocommerce", "easy-digital-downloads", "bbpress", "buddyboss",
        "learnpress", "lifterlms", "tutor", "sensei-lms",
        "gutenberg", "advanced-custom-fields", "acf", "meta-box",
        "buddypress", "wpforo", "wp-super-cache", "w3-total-cache",
        "litespeed-cache", "autoptimize", "wp-rocket", "cache-enabler",
        "redirection", "safe-redirect-manager",
    ]
    for plugin in wp_plugins:
        rows.append({
            "name": f"WordPress Plugin: {plugin}",
            "description": f"Detects WordPress plugin '{plugin}'",
            "solution": "Keep plugin updated. Remove if unused.",
            "cvss": "5.0", "severity": "Medium", "family": "Web Application",
            "type": "path", "path": f"/wp-content/plugins/{plugin}/",
            "indicator": "", "header": "", "ports": "80, 443, 8080", "cve": "",
        })

    # ── Batch 6: More WordPress Themes (10, IDs 2308-2317) ──
    wp_themes = [
        "astra", "colibri-wp", "generatepress", "oceanwp", "neve",
        "kadence", "blocksy", "hello-elementor", "storefront", "twenty-twenty-four",
    ]
    for theme in wp_themes:
        rows.append({
            "name": f"WordPress Theme: {theme}",
            "description": f"Detects WordPress theme '{theme}'",
            "solution": "Keep theme updated to latest version.",
            "cvss": "3.0", "severity": "Low", "family": "Information Gathering",
            "type": "path", "path": f"/wp-content/themes/{theme}/",
            "indicator": "", "header": "", "ports": "80, 443, 8080", "cve": "",
        })

    # ── Batch 7: More Security Header Checks (20, IDs 2318-2337) ──
    config_checks = [
        ("X-Content-Type-Options nosniff", "X-Content-Type-Options nosniff Header Check", 4.0, "Medium", "header", "", "x-content-type-options"),
        ("X-Frame-Options DENY", "X-Frame-Options DENY Header Clickjacking Protection", 5.0, "Medium", "header", "", "x-frame-options"),
        ("X-XSS-Protection Header", "X-XSS-Protection Header Legacy Browser Check", 3.0, "Low", "header", "", "x-xss-protection"),
        ("Referrer-Policy Header", "Referrer-Policy Header Privacy Check", 3.0, "Low", "header", "", "referrer-policy"),
        ("Permissions-Policy Header", "Permissions-Policy Header Feature Restriction Check", 3.0, "Low", "header", "", "permissions-policy"),
        ("Cross-Origin-Embedder-Policy", "Cross-Origin-Embedder-Policy COEP Check", 4.0, "Medium", "header", "", "cross-origin-embedder-policy"),
        ("Cross-Origin-Opener-Policy", "Cross-Origin-Opener-Policy COOP Check", 4.0, "Medium", "header", "", "cross-origin-opener-policy"),
        ("Cross-Origin-Resource-Policy", "Cross-Origin-Resource-Policy CORP Check", 3.0, "Low", "header", "", "cross-origin-resource-policy"),
        ("Timing-Allow-Origin Header", "Timing-Allow-Origin Resource Timing Check", 2.0, "Low", "header", "", "timing-allow-origin"),
        ("Accept-CH Header", "Accept-CH Client Hints Header Check", 2.0, "Low", "header", "", "accept-ch"),
        ("Critical-CH Header", "Critical-CH Critical Client Hints Check", 2.0, "Low", "header", "", "critical-ch"),
        ("X-DNS-Prefetch-Control", "X-DNS-Prefetch-Control Header Check", 1.0, "Info", "header", "", "x-dns-prefetch-control"),
        ("Expect-CT Header", "Expect-CT Certificate Transparency Check", 3.0, "Low", "header", "", "expect-ct"),
        ("Clear-Site-Data Header", "Clear-Site-Data Header Check", 2.0, "Low", "header", "", "clear-site-data"),
        ("Set-Cookie Partitioned Flag", "Partitioned Flag on Cookies (CHIPS) Check", 3.0, "Low", "cookie", "", ""),
        ("Set-Cookie Max-Age Check", "Cookie Max-Age Expiration Check", 2.0, "Low", "cookie", "", ""),
        ("Set-Cookie Domain Check", "Cookie Domain Attribute Scope Check", 3.0, "Low", "cookie", "", ""),
        ("CORS Origin Reflection", "CORS Origin Reflection Vulnerability Check", 7.0, "High", "header", "", "access-control-allow-origin"),
        ("CORS Allow-Methods", "CORS Allow-Methods Overly Permissive Check", 4.0, "Medium", "header", "", "access-control-allow-methods"),
        ("CORS Allow-Headers", "CORS Allow-Headers Overly Permissive Check", 4.0, "Medium", "header", "", "access-control-allow-headers"),
    ]
    for name, desc, cvss, sev, dtype, path, hdr in config_checks:
        rows.append({
            "name": name, "description": desc[:200],
            "solution": "Configure web server to send appropriate security headers.",
            "cvss": str(cvss), "severity": sev, "family": "Web Security",
            "type": dtype, "path": "/", "indicator": "", "header": hdr,
            "ports": "80, 443", "cve": "",
        })

    return rows


def main():
    output = Path("/tmp/opencode/batch3_plugins.csv")
    rows = make_rows()
    with open(output, "w", newline="", encoding="utf-8") as f:
        fieldnames = ["name", "description", "solution", "cvss", "severity",
                       "family", "type", "path", "indicator", "header",
                       "ports", "cve", "negate", "method", "read_size"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Generated {len(rows)} plugin definitions -> {output}")
    print(f"ID range: 2108-{2108 + len(rows) - 1}")
    print(f"CVEs: {sum(1 for r in rows if r['cve'])}")


if __name__ == "__main__":
    main()
