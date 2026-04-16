# APT41 Campaign Targeting Japanese Manufacturing Sector

## Executive Summary

In March 2026, security researchers identified a new campaign attributed to APT41
(also known as BARIUM, Winnti) targeting Japanese manufacturing companies.
The campaign leverages spear-phishing emails with malicious attachments exploiting
CVE-2025-12345, a remote code execution vulnerability in a popular document management system.

## Threat Actor Profile

APT41 is a Chinese state-sponsored threat group known for conducting espionage operations
alongside financially motivated attacks. The group has been active since at least 2012
and targets a wide range of industries including manufacturing, healthcare, and technology.

## Tactics, Techniques, and Procedures

The campaign uses the following TTPs:

1. **Initial Access**: Spear-phishing (T1566.001) with weaponized DOCX files
2. **Execution**: PowerShell scripts (T1059.001) for payload delivery
3. **Persistence**: Registry run keys (T1547.001)
4. **Credential Access**: Mimikatz for credential dumping (T1003.001)
5. **Lateral Movement**: Remote Desktop Protocol (T1021.001)
6. **Exfiltration**: Data exfiltration over HTTPS (T1041)

## Malware

The campaign deploys a custom backdoor named "ShadowPad Lite" which communicates
with C2 servers using encrypted HTTPS traffic.

## Indicators of Compromise

- Domain: update-service[.]example[.]com
- IP: 198.51.100[.]42
- Hash (SHA256): a1b2c3d4e5f6789012345678901234567890abcdef1234567890abcdef123456
