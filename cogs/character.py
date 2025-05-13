import os
import re
from sys import prefix
from typing import Union

import aiohttp
import discord
from discord.ext import commands
from discord import app_commands, Webhook

from db import get_conn
import pymysql

async def character_autocomplete(interaction: discord.Interaction, current: str):
    async with (await get_conn()).acquire() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                'SELECT name, prefix FROM characters WHERE uid = %s AND channel = %s',
                (str(interaction.user.id), str(getChannelOrForumId(interaction.channel)),))
            db_characters = await cursor.fetchall()
            print(db_characters)

    return [
        app_commands.Choice(name=f"{character[0]}({character[1]})", value=character[0])
        for character in db_characters if current == "" or current.lower() in character[0].lower()
    ]


def getChannelOrForumId(channel: Union[discord.TextChannel, discord.Thread]):
    return channel.parent_id if isinstance(channel, discord.Thread) else channel.id


async def createWebhook(channel: Union[discord.TextChannel, discord.Thread]):
    if isinstance(channel, discord.Thread):
        forum = channel.guild.get_channel(channel.parent_id)
        return await forum.create_webhook(name="Character Webhook", reason="webhook required")
    return await channel.create_webhook(name="Character Webhook", reason="webhook required")


async def getOrCreateWebhookUrl(channel: Union[discord.TextChannel, discord.Thread]):
    async with (await get_conn()).acquire() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute('SELECT url FROM webhooks WHERE channel = %s', (str(getChannelOrForumId(channel)),))
            result = await cursor.fetchone()

            if not result:
                new_webhook = await createWebhook(channel)
                await cursor.execute('INSERT INTO webhooks (channel, url) VALUES (%s, %s)',
                                     (str(new_webhook.channel_id), new_webhook.url))
                return new_webhook.url

            return result[0]


async def updateWebhook(channel: Union[discord.TextChannel, discord.Thread]):
    async with (await get_conn()).acquire() as conn:
        async with conn.cursor() as cursor:
            new_webhook = await createWebhook(channel)
            await cursor.execute('UPDATE webhooks SET url = %s WHERE channel = %s',
                                 (new_webhook.url, str(new_webhook.channel_id)))
            return new_webhook.url


class character_wh(commands.Cog, description="將訊息轉換爲角色説出的訊息"):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.author.bot:
            match = re.match(r"^(\S{1,3})\s+(.*)", message.content)
            if match:
                msg_prefix = match.group(1)
                if re.search(r"[^a-zA-Z0-9]", prefix):
                    async with (await get_conn()).acquire() as conn:
                        async with conn.cursor() as cursor:
                            channel_id = getChannelOrForumId(message.channel)
                            await cursor.execute(
                                'SELECT channel, name, picture FROM characters WHERE uid = %s AND channel = %s AND prefix = %s',
                                (str(message.author.id), str(channel_id), msg_prefix,))
                            character = await cursor.fetchone()

                    if character:
                        async def send_msg():
                            async with aiohttp.ClientSession() as session:
                                webhook = Webhook.from_url(await getOrCreateWebhookUrl(message.channel), session=session)
                                await webhook.send(username=character[1], avatar_url=character[2], content=match.group(2),
                                                   thread=message.channel if isinstance(message.channel, discord.Thread)
                                                   else discord.utils.MISSING)
                        try:
                            await send_msg()
                        except discord.NotFound:
                            await updateWebhook(message.channel)
                            await send_msg()
                        await message.delete()

    @app_commands.command(name='新增角色', description='新增一個角色')
    @app_commands.describe(cha_name="角色的名字", cha_prefix="角色的觸發詞，包含至少一個英文字、數字或符號，三個字以内",
                           cha_pf_image="角色的頭像", cha_channel="角色所在的頻道")
    async def add_character(self, interaction: discord.Interaction, cha_name: str,
                            cha_prefix: app_commands.Range[str, 1, 3],
                            cha_channel: Union[discord.ForumChannel, discord.TextChannel] = None,
                            cha_pf_image: discord.Attachment = None):

        if not re.search(r"[^a-zA-Z0-9]", prefix):
            await interaction.response.send_message("prefix需包含至少一個英文字、數字或符號", ephemeral=True)
            return

        character_data = {
            'uid': str(interaction.user.id),
            'channel': str(cha_channel.id if cha_channel else getChannelOrForumId(interaction.channel)),
            'name': cha_name,
            'picture': cha_pf_image.url if cha_pf_image else None,
            'prefix': cha_prefix,
        }
        try:
            async with (await get_conn()).acquire() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute('''
                        INSERT INTO characters (uid, channel, name, picture, prefix)
                        VALUES (%s, %s, %s, %s, %s)
                    ''', tuple(character_data.values()))
        except pymysql.err.IntegrityError:
            await interaction.response.send_message("已經有同名角色存在於此頻道，請使用其他名稱或先刪除舊的角色。", ephemeral=True)
            return

        await interaction.response.send_message("角色新建成功", ephemeral=True)

    @app_commands.command(name='編輯資料', description='編輯角色資料')
    @app_commands.autocomplete(character=character_autocomplete)
    @app_commands.describe(character="要編輯的角色", cha_name="角色的名字",
                           cha_prefix="角色的觸發詞，包含至少一個英文字、數字或符號，三個字以内",
                           cha_pf_image="角色的頭像")
    async def update_character_data(self, interaction: discord.Interaction, character: str,
                                    cha_name: str = None, cha_prefix: app_commands.Range[str, 1, 3] = None,
                                    cha_pf_image: discord.Attachment = None):

        if not re.search(r"[^a-zA-Z0-9]", prefix):
            await interaction.response.send_message("prefix需包含至少一個數字或符號", ephemeral=True)
            return

        update_data = {
            "name": cha_name,
            "prefix": cha_prefix,
            "picture": cha_pf_image.url if cha_pf_image else None,
        }

        values = []
        set_clauses = []

        for column, value in update_data.items():
            if value is not None:
                set_clauses.append(f"{column} = %s")
                values.append(value)

        if not values:
            await interaction.response.send_message("至少要更改一項參數", ephemeral=True)
            return

        values.extend([str(interaction.user.id), str(getChannelOrForumId(interaction.channel)), str(character)])

        async with (await get_conn()).acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(f'''UPDATE characters SET {", ".join(set_clauses)}
                                         WHERE uid = %s AND channel = %s AND name = %s''', values)
                if cursor.rowcount == 0:
                    await interaction.response.send_message("找不到符合條件的資料", ephemeral=True)
                else:
                    await interaction.response.send_message("成功更新資料", ephemeral=True)

    @app_commands.command(name='刪除角色', description='刪除角色資料')
    @app_commands.autocomplete(character=character_autocomplete)
    @app_commands.describe(confirm="輸入\"confirm\"來確認")
    async def delete_character(self, interaction: discord.Interaction, character: str,
                               confirm: app_commands.Range[str, 7, 7]):

        if not confirm == "confirm":
            await interaction.response.send_message("如要刪除，請在confirm欄位**一字不差**填入`confirm`", ephemeral=True)
            return

        async with (await get_conn()).acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute('DELETE FROM characters WHERE uid = %s AND channel = %s AND name = %s',
                                     (str(interaction.user.id), str(getChannelOrForumId(interaction.channel)), str(character),))
                if cursor.rowcount == 0:
                    await interaction.response.send_message("找不到符合條件的資料", ephemeral=True)
                else:
                    await interaction.response.send_message("刪除角色成功", ephemeral=True)


async def setup(bot):
    async with (await get_conn()).acquire() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute('''
                CREATE TABLE IF NOT EXISTS characters (
                    uid VARCHAR(255) NOT NULL,
                    channel VARCHAR(255) NOT NULL,
                    name VARCHAR(255) NOT NULL,
                    picture TEXT,
                    prefix VARCHAR(10) NOT NULL,
                    UNIQUE(channel, name)
                );
            ''')
            await cursor.execute('''
                CREATE TABLE IF NOT EXISTS webhooks (
                    channel VARCHAR(255) PRIMARY KEY,
                    url TEXT NOT NULL
                );
            ''')

    await bot.add_cog(character_wh(bot))
