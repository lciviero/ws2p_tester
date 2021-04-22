import requests
import websocket
import socket
import ssl
import datetime

#################
# configuration #
#################
BMA_NODE_URL = "https://duniter.lucho14.website"
BMA_PEERS_END_POINT = "/network/peers"

# stats
end_points_tested = 0
end_points_ok = 0
end_points_timeout = 0
end_points_bad_status = 0
end_points_https_invalid = 0


def get_peers():
    """return the peers known by the node"""
    req = requests.get(BMA_NODE_URL + BMA_PEERS_END_POINT)
    return req.json()['peers']


def test_ws2p(host, port, path, timeout=1):
    """test connexion to ws2p websocket"""
    if host[-1:] == '/':
        host = host[:-1]

    if port == '443':
        url = 'wss://'
    else:
        url = 'ws://'
    url += host + ':' + port + path

    print('****** testing {}'.format(url))
    ws = websocket.create_connection(url, timeout=timeout, sslopt={"cert_reqs": ssl.CERT_NONE})
    print(ws.recv())
    ws.close()

    return True


def test_end_points(peer, timeout=1):
    global end_points_tested, end_points_ok, end_points_timeout, end_points_bad_status, end_points_https_invalid

    for ep in peer['endpoints']:
        ep = ep.split()
        protocol = ep[0]

        if protocol == 'WS2P':
            # dealing with incorrect endpoint ...
            # example 'WS2P 77.152.31.154 20910',
            if len(ep) < 4:
                continue
            host = ep[2]
            port = ep[3]
            path = ''
            if len(ep) >= 5:
                path = ep[4]
            if path and path[0] != '/':
                path = '/' + path

            try:
                end_points_tested += 1
                if test_ws2p(host, port, path, timeout=timeout):
                    end_points_ok += 1
            except (socket.timeout, websocket._exceptions.WebSocketTimeoutException) as ex:
                end_points_timeout += 1
                print(ex)
            except websocket._exceptions.WebSocketBadStatusException as ex:
                end_points_bad_status += 1
                print(ex)
            except ValueError as ex:
                end_points_https_invalid += 1
                print(ex)

    return False


def main():
    peers = get_peers()
    for peer in peers:
        print('*** testing: {}'.format(peer['pubkey']))
        test_end_points(peer, timeout=1)

    print('***************')
    print('*** RESULTS ***')
    print('***************')
    print('  DateTime: {}'.format(datetime.datetime.now()))
    print('  End points tested: {}'.format(end_points_tested))
    print('  End points ok: {}'.format(end_points_ok))
    print('  Error timeout: {}'.format(end_points_timeout))
    print('  Error bad status: {}'.format(end_points_bad_status))
    print('  Error https invalid: {}'.format(end_points_https_invalid))


if __name__ == "__main__":
    main()

