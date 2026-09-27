import os
import time
import requests


class SpeakeasyClient:

    def __init__(self, base_url):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()

        self.username = os.environ.get("SPEAKEASY_USERNAME")
        self.password = os.environ.get("SPEAKEASY_PASSWORD")

        self.processed_messages = set()
        self.sent_messages = set()

    # ---------------------------------------------------------
    # Login
    # ---------------------------------------------------------

    def login(self):

        if not self.username or not self.password:
            raise RuntimeError(
                "Please set SPEAKEASY_USERNAME and "
                "SPEAKEASY_PASSWORD."
            )

        url = f"{self.base_url}/api/login"

        payload = {
            "username": self.username,
            "password": self.password
        }

        response = self.session.post(
            url,
            json=payload
        )

        response.raise_for_status()

        print("Logged into Speakeasy.")

    # ---------------------------------------------------------
    # Get rooms
    # ---------------------------------------------------------

    def get_rooms(self):

        url = f"{self.base_url}/api/rooms"

        response = self.session.get(url)

        response.raise_for_status()

        data = response.json()

        if isinstance(data, dict):
            return data.get("rooms", [])

        return data

    # ---------------------------------------------------------
    # Get messages from one room
    # ---------------------------------------------------------

    def get_room(self, room_id, since=0):

        url = f"{self.base_url}/api/room/{room_id}"

        response = self.session.get(
            url,
            params={"since": since}
        )

        response.raise_for_status()

        return response.json()

    # ---------------------------------------------------------
    # Send message
    # ---------------------------------------------------------

    def send_message(self, room_id, text):

        url = f"{self.base_url}/api/room/{room_id}"

        response = self.session.post(
            url,
            data=text,
            headers={"Content-Type": "text/plain"}
        )

        response.raise_for_status()

        self.sent_messages.add((str(room_id), text))

    # ---------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------

    def get_messages(self, room):

        if not isinstance(room, dict):
            return []

        if "messages" in room:
            return room["messages"]

        if "chatMessages" in room:
            return room["chatMessages"]

        return []

    def get_message_text(self, message):

        if not isinstance(message, dict):
            return None

        for field in ["message", "text", "content"]:

            if field in message:
                return message[field]

        return None

    def get_message_id(self, message, room_id=None):

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

        # Ordinals are unique within a room, not necessarily across rooms.
        if room_id is not None:
            return str(room_id), str(message_id)

        return message_id

    def is_bot_message(self, room, room_state, message, room_id):
        """Return whether a message was sent by a bot account."""

        if message.get("bot") is True:
            return True

        author = message.get("authorAlias")

        text = self.get_message_text(message)

        if (str(room_id), text) in self.sent_messages:
            return True

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

    # ---------------------------------------------------------
    # Process one message
    # ---------------------------------------------------------

    def process_message(self, agent, message):

        text = self.get_message_text(message)

        if not text:
            return None

        print("\nReceived:")
        print(text)

        try:

            result = agent.answer(text)

            answer = agent.format_answer(result)

            print("\nAnswer:")
            print(answer)

            return answer

        except Exception as error:

            print("SPARQL error:", error)

            return f"SPARQL error: {error}"

    # ---------------------------------------------------------
    # Main Speakeasy loop
    # ---------------------------------------------------------

    def run(self, agent, poll_interval=2):

        while True:

            try:

                rooms = self.get_rooms()

                for room in rooms:

                    if not isinstance(room, dict):
                        continue

                    room_id = (
                        room.get("id")
                        or room.get("roomId")
                        or room.get("uid")
                    )

                    if room_id is None:
                        continue

                    room_state = self.get_room(room_id)

                    messages = self.get_messages(
                        room_state
                    )

                    for message in messages:

                        message_id = self.get_message_id(
                            message,
                            room_id
                        )

                        if message_id is None:
                            continue

                        # Already answered
                        if message_id in self.processed_messages:
                            continue

                        self.processed_messages.add(
                            message_id
                        )

                        # Avoid answering bot-generated messages.
                        if self.is_bot_message(
                            room,
                            room_state,
                            message,
                            room_id
                        ):
                            continue

                        answer = self.process_message(
                            agent,
                            message
                        )

                        if answer:

                            self.send_message(
                                room_id,
                                answer
                            )

                time.sleep(poll_interval)

            except KeyboardInterrupt:

                print("\nBot stopped.")
                break

            except requests.RequestException as error:

                print(
                    "Speakeasy API error:",
                    error
                )

                time.sleep(5)

            except Exception as error:

                print(
                    "Unexpected error:",
                    error
                )

                time.sleep(5)
