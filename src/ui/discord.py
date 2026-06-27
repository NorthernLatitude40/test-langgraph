import discord
from src.core.harness import AgentHarness
from src.config.config import DISCORD_TOKEN
import asyncio

TOKEN = DISCORD_TOKEN

intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)

harness = None


@client.event
async def on_ready():
    global harness

    print("初始化 Harness...")
    harness = AgentHarness()
    harness.bootstrap()
    print("Harness 初始化完成")

    print(f"登录成功：{client.user}")


@client.event
async def on_message(message):
    if message.author.bot:
        return

    reply = await asyncio.to_thread(
        harness.interact, message.content, thread_id=str(message.author.id)
    )

    await message.channel.send(reply)


client.run(TOKEN)
