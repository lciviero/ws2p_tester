# -*- coding: utf-8 -*-

import asyncio
import aiohttp
import jsonschema
import coloredlogs, logging
from jsonschema import ValidationError
from _socket import gaierror
from collections import defaultdict
from typing import Union, List

from duniterpy import key
from duniterpy.helpers import network
from duniterpy.api.client import Client
from duniterpy.helpers.ws2p import handshake
from duniterpy.api.endpoint import BMAEndpoint, SecuredBMAEndpoint, WS2PEndpoint
from duniterpy.documents.document import MalformedDocumentError
from duniterpy.api import bma

#################
# configuration #
#################
# BMAS_ENDPOINT = "BMAS duniter.lucho14.website 443"
# BMAS_ENDPOINT = "BMAS g1.duniter.org 443"
BMAS_ENDPOINT = "BMAS g1.cgeek.fr 443"
ES_USER_ENDPOINT = "ES_USER_API g1.data.presles.fr 443"
CURRENCY = "g1"

# logging config
coloredlogs.install(level='INFO')
logging.basicConfig(format='%(asctime)s %(levelname)s %(message)s', level=logging.INFO)


async def test_ws2p_ws(client_ws2p: Client, signing_key: key.signing_key.SigningKeyType) -> (bool, str):
    """Test the websocket of a ws2p client"""

    logging.info('*** trying : {} ...'.format(client_ws2p.endpoint))
    error = False
    error_str = ''
    try:
        # Create a Web Socket connection
        ws = await client_ws2p.connect_ws()
        logging.info('connected ... ')
        try:
            # Trying a handshake
            await handshake(ws, signing_key, CURRENCY)
            error_str = 'handshake ok !'
            logging.info(error_str)
        except TypeError as ex:
            error_str = ex
            logging.warning(error_str)
            error = True
        except ValidationError as ex:
            error_str = ex.message
            logging.warning(error_str)
            error = True

    except (aiohttp.WSServerHandshakeError, ValueError) as e:
        error_str = "Websocket handshake {0} : {1}".format(type(e).__name__, str(e))
        logging.warning(error_str)
        error = True
    except (aiohttp.ClientError, gaierror, TimeoutError) as e:
        error_str = "{0} : {1}".format(str(e), client_ws2p.endpoint)
        logging.warning(error_str)
        error = True
    except jsonschema.ValidationError as e:
        error_str = "{:}:{:}".format(str(e.__class__.__name__), str(e))
        logging.warning(error_str)
        error = True

    await client_ws2p.close()

    return not error, error_str


async def get_ws2p_endpoints(bma_endpoint: Union[str, BMAEndpoint, SecuredBMAEndpoint]) -> List[WS2PEndpoint]:
    """
    Return the list of WS2P endpoints for a BMA endpoint
    """
    ws2p_endpoints = list()
    bma_client = Client(bma_endpoint)
    try:
        peering = await bma_client(bma.network.peering)
    except Exception as ex:
        await bma_client.close()
        raise ex

    for endpoint in peering["endpoints"]:
        if endpoint.startswith("WS2P"):
            ws2p_endpoints.append(WS2PEndpoint.from_inline(endpoint))

    await bma_client.close()

    return ws2p_endpoints


async def main():
    """
    Main
    """
    # dummy credentials
    salt = password = "test"
    # Init signing_key instance
    signing_key = key.SigningKey.from_credentials(salt, password)

    # Create client to retrieve nodes list
    bmas_client = Client(BMAS_ENDPOINT)

    # get nodes list
    try:
        groups = await network.get_available_nodes(bmas_client)
    except (aiohttp.client_exceptions.ClientConnectorError, asyncio.exceptions.TimeoutError, ValueError) as ex:
        logging.error('ERROR: unable to retrieved available nodes !')
        logging.error(ex)
        await bmas_client.close()
        exit(1)

    await bmas_client.close()

    # list of endpoint in error by pubkey
    error_nodes = defaultdict(list)

    # loop on each group of nodes
    for group in groups:
        # loop on each node of each group
        for node in group:
            logging.debug('testing: {}'.format(node['head'].pubkey))

            for endpoint in node['endpoints']:
                if endpoint.startswith('BMAS') or endpoint.startswith('BASIC_MERKLED_API'):
                    logging.info('retrieving ws2p endpoints from {}'.format(endpoint))
                    try:
                        ws2p_endpoints = await get_ws2p_endpoints(endpoint)
                    except (asyncio.TimeoutError, aiohttp.client_exceptions.ClientConnectorError) as ex:
                        error_str = 'unable to retrieved WS2P endpoint: {}'.format(ex)
                        error_nodes[node['head'].pubkey].append((endpoint, error_str))
                        logging.warning(error_str)
                    except MalformedDocumentError as ex:
                        error_str = 'Malformed WS2P endpoint: {}'.format(ex)
                        error_nodes[node['head'].pubkey].append((endpoint, error_str))
                        logging.warning(error_str)
                    except ValueError as ex:
                        error_str = 'unable to retrieved WS2P endpoint, value error: {}'.format(ex)
                        error_nodes[node['head'].pubkey].append((endpoint, error_str))
                        logging.warning(error_str)
                    else:
                        for ws2p_endpoint in ws2p_endpoints:
                            ws2p_client = Client(ws2p_endpoint)
                            res, error_str = await test_ws2p_ws(ws2p_client, signing_key)
                            if not res:
                                # add ep in error for this pubkey
                                error_nodes[node['head'].pubkey].append((ws2p_endpoint.inline(), error_str))
                        break

    # errors report
    # client to retrieve the name associated to the public key
    client_es = Client(ES_USER_ENDPOINT)
    for pubkey, endpoints in error_nodes.items():
        # retrieve user name associated to public key
        try:
            username = await client_es.get("user/profile/{}/_source".format(pubkey.strip(" \n")))
            print('{} - {}'.format(username['title'], pubkey))
        except ValueError as ex:
            print('{} - {}'.format('unknown', pubkey))

        for endpoint in endpoints:
            print('   {}: {}'.format(endpoint[0], endpoint[1]))

    await client_es.close()

asyncio.get_event_loop().run_until_complete(main())
