import http.client
import mimetypes
import base64
import os
import orjson

DATA_CENTER = "iad1"
CLIENT_ID = os.getenv("QUALTRICS_CLIENT_ID")
CLIENT_SECRET = os.getenv("QUALTRICS_OAUTH_SECRET")

def __list_to_scope_string(scopes: list[str]):
    """Private member. Do not use.

    Gets a scope string from a list of scopes passed into `get_bearer_token`.
    Args:
        scopes (list[str]): List of scopes requested.

    Returns:
        str: Space separated scope string, able to be passed into HTTP request.
    """
    return ' '.join(scopes)

def get_bearer_token(scopes=["read:users","read:surveys"]):
    """Get a bearer token from Qualtrics based on provided OAUTH2 scopes.

    Args:
        scopes (list[str], optional): List of scopes to request a token for. Defaults to ["read:users","read:surveys"].
    """
    
    auth = f"{CLIENT_ID}:{CLIENT_SECRET}"
    encodedBytes=base64.b64encode(auth.encode("utf-8"))
    authStr = str(encodedBytes, "utf-8")

    #create the connection 
    conn = http.client.HTTPSConnection(f"{DATA_CENTER}.qualtrics.com")
    scope_string = __list_to_scope_string(scopes)
    body = f"grant_type=client_credentials&scope={scope_string}"
    headers = {
    'Content-Type': 'application/x-www-form-urlencoded'
    }
    headers['Authorization'] = f"Basic {authStr}"

    #make the request
    conn.request("POST", "/oauth2/token", body, headers)
    res = conn.getresponse()
    raw = res.read().decode("utf-8")
    data = orjson.loads(raw)

    if data['access_token']:
        return data['access_token']
    else: 
        print(raw)
        raise http.client.HTTPException("Invalid request. Response did not include bearer token.")
