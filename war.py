
"""
war card game client and server
"""
import asyncio
from collections import namedtuple
from enum import Enum
import logging
import random
import socket
import socketserver
import threading
import sys

#bonus
from concurrent.futures import ThreadPoolExecutor

# Initialize the pool with a limit
executor = ThreadPoolExecutor(max_workers=600)  # Limits to 600 threads/games


"""
Namedtuples work like classes, but are much more lightweight so they end
up being faster. It would be a good idea to keep objects in each of these
for each game which contain the game's state, for instance things like the
socket, the cards given, the cards still available, etc.
"""
Game = namedtuple("Game", ["p1", "p2"])

# Stores the clients waiting to get connected to other clients
waiting_clients = []

logging.basicConfig(level=logging.DEBUG)

class Command(Enum):
    """
    The byte values sent as the first byte of any message in the war protocol.
    """
    WANTGAME = 0
    GAMESTART = 1
    PLAYCARD = 2
    PLAYRESULT = 3

class Result(Enum):
    """
    The byte values sent as the payload byte of a PLAYRESULT message.
    """
    WIN = 0
    DRAW = 1
    LOSE = 2

def readexactly(sock, numbytes, timeout = 10):
    """
    Accumulate exactly `numbytes` from `sock` and return those. If EOF is found
    before numbytes have been received, be sure to account for that here or in
    the caller.
    """

    #data = bytearray()
    #while len(data) < numbytes:
     #   chunk = sock.recv(numbytes - len(data))
      #  if not chunk:
            # Client disconnected or EOF before we got everything
       #     return None
        #data.extend(chunk)
    #return bytes(data)
    
    data = bytearray()
    sock.settimeout(timeout)
    try:
        while len(data) < numbytes:
            chunk = sock.recv(numbytes - len(data))
            if not chunk:
                return None
            data.extend(chunk)
    except socket.timeout:
        logging.error("Socket read timed out, terminating game.")
        return None
    finally:
        sock.settimeout(None)  # Reset
    return bytes(data)



def kill_game(game):
    """
    TODO: If either client sends a bad message, immediately nuke the game.
    """
    logging.debug("Killing game due to protocol error.")
    try:
        game.p1.close()
    except Exception as e:
        logging.error("Error closing p1: %s", e)
    try:
        game.p2.close()
    except Exception as e:
        logging.error("Error closing p2: %s", e)

def compare_cards(card1, card2):
    """
    TODO: Given an integer card representation, return -1 for card1 < card2,
    0 for card1 = card2, and 1 for card1 > card2
    """
    c1 = card1 % 13
    c2 = card2 % 13
    if c1 < c2:
        return -1
    if c1 > c2:
        return 1
    else: 
        return 0
    

def deal_cards():
    """
    TODO: Randomize a deck of cards (list of ints 0..51), and return two
    26 card "hands."
    """

    doc = list(range(52))
    random.shuffle(doc)
    hand1 = doc[:26]
    hand2 = doc[26:]
    return (hand1, hand2)

def serve_game(host, port):
    """
    TODO: Open a socket for listening for new connections on host:port, and
    perform the war protocol to serve a game of war between each client.
    This function should run forever, continually serving clients.
    """
    
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_sock.bind((host, port))
    server_sock.listen(1000)
    logging.info(f"Server listening on {host}:{port}")
    


    game_number = 0
    try:
        while True:
            client_sock, addr = server_sock.accept()
            logging.debug(f"Accepted connection from {addr}")
            waiting_clients.append(client_sock)

            # Pair up when there are two clients
            if len(waiting_clients) >= 2:
                p1 = waiting_clients.pop(0)
                p2 = waiting_clients.pop(0)
                game = Game(p1, p2)
                #instead of making a new thread for every game, uses the pool
                #threading.Thread(target=run_game, args=(game,), daemon=True).start()
                game_number += 1
                logging.info(f"Game Number {game_number}")
                executor.submit(run_game, game)
    finally:
        server_sock.close()

def run_game(game):
    """
    Run a single game of WAR between two clients. helper function for serve_game
    """
    try:
        # Step 1: Wait for WANTGAME (2 bytes: command=0, payload=0)
        msg1 = readexactly(game.p1, 2)
        msg2 = readexactly(game.p2, 2)
        if not msg1 or not msg2 or msg1[0] != Command.WANTGAME.value or msg2[0] != Command.WANTGAME.value:
            logging.warning("One or both clients did not send valid WANTGAME.")
            kill_game(game)
            return

        # Step 2: Deal cards and send GAMESTART
        hand1, hand2 = deal_cards()
        game_start_msg1 = bytes([Command.GAMESTART.value]) + bytes(hand1)
        game_start_msg2 = bytes([Command.GAMESTART.value]) + bytes(hand2)
        game.p1.sendall(game_start_msg1)
        game.p2.sendall(game_start_msg2)

        # Step 3: Play 26 rounds
        for i in range(26):
            move1 = readexactly(game.p1, 2)
            move2 = readexactly(game.p2, 2)

            if not move1 or not move2 or move1[0] != Command.PLAYCARD.value or move2[0] != Command.PLAYCARD.value:
                logging.warning("One or both clients sent invalid PLAYCARD.")
                kill_game(game)
                return

            c1 = move1[1]
            c2 = move2[1]
            cmp = compare_cards(c1, c2)

            if cmp == 1:
                result1, result2 = Result.WIN.value, Result.LOSE.value
            elif cmp == -1:
                result1, result2 = Result.LOSE.value, Result.WIN.value
            else:
                result1 = result2 = Result.DRAW.value

            msg1 = bytes([Command.PLAYRESULT.value, result1])
            msg2 = bytes([Command.PLAYRESULT.value, result2])
            game.p1.sendall(msg1)
            game.p2.sendall(msg2)

        # Step 4: Close connections cleanly
        logging.debug("Game complete, closing connections.")
        game.p1.close()
        game.p2.close()

    except Exception as e:
        logging.error("Error during game: %s", e)
        kill_game(game)


    

async def limit_client(host, port, loop, sem):
    """
    Limit the number of clients currently executing.
    You do not need to change this function.
    """
    async with sem:
        return await client(host, port, loop)

async def client(host, port, loop):
    """
    Run an individual client on a given event loop.
    You do not need to change this function.
    """
    try:
        reader, writer = await asyncio.open_connection(host, port)
        # send want game
        writer.write(b"\0\0")
        card_msg = await reader.readexactly(27)
        myscore = 0
        for card in card_msg[1:]:
            writer.write(bytes([Command.PLAYCARD.value, card]))
            result = await reader.readexactly(2)
            if result[1] == Result.WIN.value:
                myscore += 1
            elif result[1] == Result.LOSE.value:
                myscore -= 1
        if myscore > 0:
            result = "won"
        elif myscore < 0:
            result = "lost"
        else:
            result = "drew"
        logging.debug("Game complete, I %s", result)
        writer.close()
        return 1
    except ConnectionResetError:
        logging.error("ConnectionResetError")
        return 0
    except asyncio.IncompleteReadError:
        logging.error("asyncio.streams.IncompleteReadError")
        return 0
    except OSError:
        logging.error("OSError")
        return 0
    
async def client_batch(host, port, num_clients):
    """Handles the batch running of clients with success and failure tracking."""
    successful_games = 0
    failed_games = 0

    async def delayed_client(i):
        await asyncio.sleep(i * 0.01)  # Staggering connections to avoid burst
        result = await client(host, port, asyncio.get_event_loop())
        return result

    tasks = [delayed_client(i) for i in range(num_clients)]

    # Iterate through all completed tasks
    for task in asyncio.as_completed(tasks):
        result = await task
        if result == 1:
            successful_games += 0.5
        else:
            failed_games += 0.5

    # 🟢 Added Final Count Log
    logging.info(f"{num_clients} clients served.")

def main(args):
    """
    launch a client/server
    """
    print("main called with:", args)

    host = args[1]
    port = int(args[2])
    if args[0] == "server":
        try:
            # your server should serve clients until the user presses ctrl+c
            serve_game(host, port)
        except KeyboardInterrupt:
            pass
        return
    else:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
        
        asyncio.set_event_loop(loop)
        
    if args[0] == "client":
        loop.run_until_complete(client(host, port, loop))
    elif args[0] == "clients":
        num_clients = int(args[3])
        loop.run_until_complete(client_batch(host, port, num_clients))

        
        #sem = asyncio.Semaphore(1000)
        #num_clients = int(args[3])
        
        #clients = [limit_client(host, port, loop, sem) for _ in range(num_clients)]

        #loop.run_until_complete(asyncio.gather(*clients))
    loop.close()

if __name__ == "__main__":
    # Changing logging to DEBUG
    logging.basicConfig(level=logging.DEBUG)
    main(sys.argv[1:])
