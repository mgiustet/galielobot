import sys
from telethon import TelegramClient, events
from telethon.sessions import StringSession

def update_status(is_up):
    #main method (and the only one that should be invoked from outside this module). Update bot description basing on the boolean is_up
    print(is_up)

    f1 = open("ID&HASH.txt", "r")
    f2 = open("STRING_SESSION.txt", "r")
    text1 = f1.read().split("\n")
    text2 = f2.read().split("\n")
    API_ID = text1[0]
    API_HASH = text1[1]
    STRING_SESSION = text2[0]
    USERNAME = "@GaliELO_bot"
    f1.close()
    f2.close()

    general_descr = "Interact with the GaliELO database.\n\nStatus: {}\nSource code: https://github.com/mgiustet/galielobot"
    strings = [u"DOWN \U0001F534", u"UP \U0001F7E2"]
    client = TelegramClient(StringSession(STRING_SESSION), API_ID, API_HASH)

    async def _main():
        await client.send_message("@BotFather", "/setabouttext")

    @client.on(events.NewMessage(incoming=True, from_users="@BotFather"))
    async def _event_handler(event):
        print(event.raw_text)
        if "Choose a bot to change the about section" in event.raw_text:
            await client.send_message("@BotFather", USERNAME)
        elif "Send me the new 'About' text" in event.raw_text:
            await client.send_message("@BotFather", general_descr.format(strings[int(is_up)]))
        elif "Success! About section updated" in event.raw_text:
            await client.send_message("me", "Set {} status to {}".format(USERNAME, strings[int(is_up)]))
            await client.disconnect()

    with client:
        client.loop.run_until_complete(_main())
    client.start()
    client.run_until_disconnected()
