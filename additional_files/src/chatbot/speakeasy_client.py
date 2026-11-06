import os
import signal
import time

import requests


class SpeakeasyClient:
    """Minimal Speakeasy HTTP client for the ATAI bot."""

    def __init__(self, base_url, request_timeout=(5, 20)):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.request_timeout = request_timeout
        self.username = os.environ.get("SPEAKEASY_USERNAME")
        self.password = os.environ.get("SPEAKEASY_PASSWORD")
        self.processed_messages = set()
        self.sent_messages = set()
        self.inactive_rooms = set()

    def login(self):
        if not self.username or not self.password:
            raise RuntimeError(
                "Please set SPEAKEASY_USERNAME and SPEAKEASY_PASSWORD."
            )

        response = self.session.post(
            f"{self.base_url}/api/login",
            json={"username": self.username, "password": self.password},
            timeout=self.request_timeout,
        )
        response.raise_for_status()
        print("Logged into Speakeasy.")

    def get_rooms(self):
        response = self.session.get(
            f"{self.base_url}/api/rooms",
            timeout=self.request_timeout,
        )
        response.raise_for_status()
        data = response.json()
        if isinstance(data, dict):
            return data.get("rooms", [])
        if isinstance(data, list):
            return data
        return []

    def get_room(self, room_id, since=0):
        response = self.session.get(
            f"{self.base_url}/api/room/{room_id}",
            params={"since": since},
            timeout=self.request_timeout,
        )
        response.raise_for_status()
        return response.json()

    def send_message(self, room_id, text):
        response = self.session.post(
            f"{self.base_url}/api/room/{room_id}",
            data=text,
            headers={"Content-Type": "text/plain"},
            timeout=self.request_timeout,
        )
        response.raise_for_status()
        self.sent_messages.add((str(room_id), text))

    @staticmethod
    def get_messages(room):
        if not isinstance(room, dict):
            return []
        if isinstance(room.get("messages"), list):
            return room["messages"]
        if isinstance(room.get("chatMessages"), list):
            return room["chatMessages"]
        return []

    @staticmethod
    def get_message_text(message):
        if not isinstance(message, dict):
            return None
        for field in ("message", "text", "content"):
            value = message.get(field)
            if isinstance(value, str):
                return value
        return None

    @staticmethod
    def get_message_id(message, room_id=None):
        if not isinstance(message, dict):
            return None
        message_id = (
            message.get("id")
            or message.get("messageId")
            or message.get("ordinal")
            or message.get("timeStamp")
        )
        if message_id is None:
            return None
        if room_id is not None:
            return str(room_id), str(message_id)
        return str(message_id)

    def is_bot_message(self, room, room_state, message, room_id):
        if not isinstance(message, dict):
            return False
        if message.get("bot") is True:
            return True

        text = self.get_message_text(message)
        if text is not None and (str(room_id), text) in self.sent_messages:
            return True

        author = message.get("authorAlias")
        if not author:
            return False

        bot_aliases = set()
        sources = [room, room_state]
        if isinstance(room_state, dict):
            sources.append(room_state.get("info"))

        for source in sources:
            if not isinstance(source, dict):
                continue
            for field in ("testerBotAlias", "botAlias"):
                alias = source.get(field)
                if alias:
                    bot_aliases.add(str(alias))

        return str(author) in bot_aliases

    @staticmethod
    def is_sparql_message(text):
        if not isinstance(text, str):
            return False
        meaningful = []
        for line in text.strip().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            meaningful.append(line)
        if not meaningful:
            return False
        first = meaningful[0].upper()
        return first.startswith(
            ("PREFIX", "BASE", "SELECT", "ASK", "CONSTRUCT", "DESCRIBE")
        )

    @classmethod
    def is_question_message(cls, text):
        """Keep old chat answers from being reprocessed after a restart."""
        if not isinstance(text, str):
            return False

        stripped = text.strip()
        if not stripped:
            return False

        if cls.is_sparql_message(stripped):
            return True

        lowered = stripped.casefold()
        if "?" in stripped:
            return True

        question_starts = (
            "who ", "what ", "when ", "where ", "which ", "how ", "please ",
            "tell me ", "name ", "give me ", "factual approach",
        )
        return lowered.startswith(question_starts)

    def process_message(self, agent, message):
        text = self.get_message_text(message)
        if text is None:
            return None
        text = text.strip()

        debug = os.environ.get("DEBUG_LOGGING", "").lower() in {"1", "true", "yes"}
        if debug:
            print("\nReceived:")
            print(text)

        timeout_seconds = float(os.environ.get("MESSAGE_TIMEOUT_SECONDS", "5"))

        class MessageTimeout(Exception):
            pass

        def timeout_handler(signum, frame):
            raise MessageTimeout

        previous_handler = signal.getsignal(signal.SIGALRM)
        signal.signal(signal.SIGALRM, timeout_handler)
        signal.setitimer(signal.ITIMER_REAL, timeout_seconds)
        try:
            answer = agent.handle_message(text)
        except MessageTimeout:
            answer = (
                "Sorry, that took too long to process. "
                "Please try a shorter movie-related question."
            )
        except Exception as error:
            if os.environ.get("DEBUG_LOGGING", "").lower() in {"1", "true", "yes"}:
                print("Message processing error:", error)
            answer = "Sorry, I could not process that question."
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, previous_handler)

        if debug:
            print("\nAnswer:")
            print(answer)
        return answer

    def run(self, agent, poll_interval=2):
        """Poll assigned rooms and answer user questions."""
        while True:
            try:
                rooms = self.get_rooms()

                for room in rooms:
                    if not isinstance(room, dict):
                        continue

                    room_id = room.get("id") or room.get("roomId") or room.get("uid")
                    if room_id is None:
                        continue
                    room_key = str(room_id)
                    if room_key in self.inactive_rooms:
                        continue

                    try:
                        room_state = self.get_room(room_id)
                    except requests.HTTPError as error:
                        status = (
                            error.response.status_code
                            if error.response is not None
                            else None
                        )
                        if status in (400, 404, 409):
                            self.inactive_rooms.add(room_key)
                            continue
                        raise

                    for message in self.get_messages(room_state):
                        message_id = self.get_message_id(message, room_id)
                        if message_id is None or message_id in self.processed_messages:
                            continue

                        if self.is_bot_message(room, room_state, message, room_id):
                            self.processed_messages.add(message_id)
                            continue

                        answer = self.process_message(agent, message)
                        if answer is None:
                            self.processed_messages.add(message_id)
                            continue

                        try:
                            self.send_message(room_id, answer)
                            self.processed_messages.add(message_id)
                        except requests.HTTPError as error:
                            status = (
                                error.response.status_code
                                if error.response is not None
                                else None
                            )
                            if status in (400, 404, 409):
                                self.inactive_rooms.add(room_key)
                                self.processed_messages.add(message_id)
                                continue
                            raise

                time.sleep(poll_interval)

            except KeyboardInterrupt:
                print("\nBot stopped.")
                break
            except requests.RequestException as error:
                print("Speakeasy API error:", error)
                time.sleep(5)
            except Exception as error:
                print("Unexpected error:", error)
                time.sleep(5)
