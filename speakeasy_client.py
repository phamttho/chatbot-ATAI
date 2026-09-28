import os
import time

import requests


class SpeakeasyClient:
    """Minimal Speakeasy HTTP client used by the working Stage 1 prototype."""

    def __init__(self, base_url, request_timeout=(5, 20)):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.request_timeout = request_timeout

        self.username = os.environ.get("SPEAKEASY_USERNAME")
        self.password = os.environ.get("SPEAKEASY_PASSWORD")

        # IDs are stored as (room_id, message_id), so simultaneous rooms work.
        self.processed_messages = set()
        self.sent_messages = set()

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
        return data if isinstance(data, list) else []

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

    def process_message(self, agent, message):
        text = self.get_message_text(message)
        if text is None:
            return None

        print("\nReceived:")
        print(text)

        try:
            if hasattr(agent, "handle_message"):
                answer = agent.handle_message(text)
            else:
                result = agent.answer(text)
                answer = agent.format_answer(result)
        except Exception as error:
            # The outer loop must stay alive even if one message is malformed.
            print("Message processing error:", error)
            answer = "Sorry, I could not process that SPARQL query."

        print("\nAnswer:")
        print(answer)
        return answer

    def run(self, agent, poll_interval=2):
        """Poll all assigned rooms and answer unprocessed human messages."""
        while True:
            try:
                rooms = self.get_rooms()

                for room in rooms:
                    if not isinstance(room, dict):
                        continue

                    room_id = room.get("id") or room.get("roomId") or room.get("uid")
                    if room_id is None:
                        continue

                    room_state = self.get_room(room_id)
                    messages = self.get_messages(room_state)

                    for message in messages:
                        message_id = self.get_message_id(message, room_id)
                        if message_id is None or message_id in self.processed_messages:
                            continue

                        # Bot messages can safely be marked as seen immediately.
                        if self.is_bot_message(room, room_state, message, room_id):
                            self.processed_messages.add(message_id)
                            continue

                        answer = self.process_message(agent, message)

                        if answer is None:
                            self.processed_messages.add(message_id)
                            continue

                        # Important: only mark a human message processed after the
                        # reply was successfully posted. If the POST fails, the next
                        # poll can retry instead of silently losing the answer.
                        self.send_message(room_id, answer)
                        self.processed_messages.add(message_id)

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
