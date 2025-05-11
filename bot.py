# !/usr/bin/python 
# coding:utf-8 
import os
from threading import Thread

import discord

from discord.ext import commands
from discord import app_commands

import dotenv
dotenv.load_dotenv('.env')

owners = [881312396784840744]
intents = discord.Intents().all()
intents.presences = False
activity = discord.Activity(type=discord.ActivityType.playing, name="施放星爆氣流斬！")


class abot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix=[],
                         activity=activity,
                         help_command=None,
                         owner_ids=set(owners),
                         intents=intents)

    async def setup_hook(self):
        for file in os.listdir('cogs'):
            if file.endswith('.py'):
                await self.load_extension('cogs.' + file[:-3])
        await self.tree.sync()

    # 當機器人完成啟動時
    async def on_ready(self):
        print('> 目前登入身份：', bot.user)
        print('> Bot is now running.')


bot = abot()


def is_owner(interaction: discord.Interaction) -> bool:
    return interaction.user.id in owners

bot.is_owner = is_owner

@bot.tree.command()
@app_commands.check(is_owner)
async def reload(interaction: discord.Interaction, cog: str) -> None:
    await bot.reload_extension("cogs." + cog)
    await interaction.response.send_message(f"重新載入{cog}完成!")
    await bot.tree.sync()


@bot.tree.command()
@app_commands.check(is_owner)
async def load(interaction: discord.Interaction, cog: str) -> None:
    await bot.load_extension("cogs." + cog)
    await interaction.response.send_message(f"載入{cog}完成!")
    await bot.tree.sync()


@bot.tree.command()
@app_commands.check(is_owner)
async def unload(interaction: discord.Interaction, cog: str) -> None:
    await bot.unload_extension("cogs." + cog)
    await interaction.response.send_message(f"卸載{cog}完成!")
    await bot.tree.sync()

if __name__ == '__main__':
    # t = Thread(target=start_ws, daemon=True)
    # t.start()
    bot.run(os.getenv('DISCORD_BOT_TOKEN'))
