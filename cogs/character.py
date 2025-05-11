import os
import re
from sys import prefix
from typing import Union

import aiohttp
import discord
from discord.ext import commands
from discord import app_commands, Webhook
import sqlite3

db_path = os.getenv('SQL_PATH')


async def character_autocomplete(interaction: discord.Interaction, current: str, ):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute(
        'SELECT name, prefix FROM characters WHERE uid = ? AND channel = ?',
        (str(interaction.user.id), str(interaction.channel.id),))
    db_characters = cursor.fetchall()
    conn.close()
    # name:"{name}({prefix})", value:"{channel_id} {name}"
    return [
        app_commands.Choice(name=f"{character[0]}({character[1]})", value=character[0])
        for character in db_characters if current == "" or current.lower() in character[0].lower()
    ]


# class Confirm(discord.ui.View):
#     def __init__(self):
#         super().__init__()
#         self.value = None
#
#     # When the confirm button is pressed, set the inner value to `True` and
#     # stop the View from listening to more input.
#     # We also send the user an ephemeral message that we're confirming their choice.
#     @discord.ui.button(label='Confirm', style=discord.ButtonStyle.green)
#     async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
#         await interaction.response.send_message('Confirming', ephemeral=True)
#         self.value = True
#         self.stop()
#
#     # This one is similar to the confirmation button except sets the inner value to `False`
#     @discord.ui.button(label='Cancel', style=discord.ButtonStyle.grey)
#     async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
#         await interaction.response.send_message('Cancelling', ephemeral=True)
#         self.value = False
#         self.stop()


def getChannelOrForumId(channel: Union[discord.TextChannel, discord.Thread]):
    if isinstance(channel, discord.Thread):
        channel_id = channel.parent_id
    else:
        channel_id = channel.id

    return channel_id


async def createWebhook(channel: Union[discord.TextChannel, discord.Thread]):
    # if type of channel is discord.Thread
    if isinstance(channel, discord.Thread):
        forum = channel.guild.get_channel(channel.parent_id)
        _webhook = await forum.create_webhook(name="Character Webhook", reason="webhook required")
    else:
        _webhook = await channel.create_webhook(name="Character Webhook", reason="webhook required")
    return _webhook


async def getOrCreateWebhookUrl(channel: Union[discord.TextChannel, discord.Thread]):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute('SELECT url FROM webhooks WHERE channel = ?', (str(channel.id),))
    webhook_url = cursor.fetchone()
    print(webhook_url)

    if not webhook_url:
        new_webhook = await createWebhook(channel)
        cursor.execute('INSERT INTO webhooks (channel, url) VALUES (?, ?)',
                       (str(new_webhook.channel_id), new_webhook.url))
        conn.commit()
        conn.close()

        return new_webhook
    webhook_url = webhook_url[0]
    conn.close()
    return webhook_url


async def updateWebhook(channel: Union[discord.TextChannel, discord.Thread]):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    new_webhook = await createWebhook(channel)
    cursor.execute('UPDATE webhooks SET url = ? WHERE channel = ?',
                   (new_webhook.url, str(new_webhook.channel_id)))

    conn.commit()
    conn.close()

    return new_webhook.url


class character_wh(commands.Cog, description="將訊息轉換爲角色説出的訊息"):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.author.bot:
            # 檢查開頭是否符合條件
            match = re.match(r"^(\S{1,3})\s+(.*)", message.content)
            if match:
                msg_prefix = match.group(1)
                # 檢查開頭的prefix至少包含一個符號
                if re.search(r"[^a-zA-Z0-9]", prefix):
                    conn = sqlite3.connect(db_path)
                    cursor = conn.cursor()

                    channel_id = getChannelOrForumId(message.channel)

                    cursor.execute(
                        'SELECT channel, name, picture FROM characters WHERE uid = ? AND channel = ? AND prefix = ?',
                        (str(message.author.id), str(channel_id), msg_prefix,))
                    character = cursor.fetchone()

                    print(character)
                    if character:
                        # await message.reply(f"{character[0]}, {character[1]}")

                        async def send_msg():
                            async with aiohttp.ClientSession() as session:
                                webhook = Webhook.from_url(await getOrCreateWebhookUrl(message.channel),
                                                           session=session)

                                await webhook.send(username=character[1], avatar_url=character[2],
                                                   content=match.group(2),
                                                   thread=message.channel if isinstance(message.channel,
                                                                                        discord.Thread) else discord.utils.MISSING)

                        try:
                            await send_msg()
                        except discord.NotFound:
                            await updateWebhook(message.channel)
                            await send_msg()

                        await message.delete()

                    # conn.commit()
                    conn.close()

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

        # try:
        character_data = {
            'uid': str(interaction.user.id),
            'channel': str(cha_channel.id if cha_channel else getChannelOrForumId(interaction.channel)),
            'name': cha_name,
            'picture': cha_pf_image.url if cha_pf_image else None,
            'prefix': cha_prefix,
        }

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute('''
            INSERT INTO characters (uid, channel, name, picture, prefix)
            VALUES (:uid, :channel, :name, :picture, :prefix)
        ''', character_data)

        conn.commit()
        conn.close()

        await interaction.response.send_message("角色新建成功", ephemeral=True)
        # except Exception as e:
        #     await interaction.response.send_message("親，這邊資料儲存失敗了喔")

    # @app_commands.command(name='編輯頭像', description='編輯角色頭像')
    # @app_commands.autocomplete(character=character_autocomplete)
    # # @app_commands.describe(cha_name="", cha_pf_image="", cha_prefix="")
    # async def update_character_pfp(self, interaction: discord.Interaction, character: str,
    #                                cha_pf_image: discord.Attachment):
    #
    #     conn = sqlite3.connect(db_path)
    #     cursor = conn.cursor()
    #
    #     cursor.execute('UPDATE characters SET picture = ? WHERE uid = ? AND channel = ? AND name = ?',
    #                    (cha_pf_image.url, str(interaction.user.id), str(interaction.channel_id), str(character),))
    #     if cursor.rowcount == 0:
    #         await interaction.response.send_message("找不到符合條件的資料", ephemeral=True)
    #         print("找不到符合條件的資料，沒有更新任何內容")
    #     else:
    #         await interaction.response.send_message("成功更新資料", ephemeral=True)
    #         print("成功更新資料")
    #         conn.commit()
    #
    #     conn.close()

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

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        update_data = {
            "name": cha_name,
            "prefix": cha_prefix,
            "picture": cha_pf_image.url if cha_pf_image else None,
        }

        values = []
        set_clauses = []

        for column, value in update_data.items():
            if value is not None:
                set_clauses.append(f"{column} = ?")
                values.append(value)

        if not values:
            await interaction.response.send_message("至少要更改一項參數", ephemeral=True)
            return

        values.extend([str(interaction.user.id), str(interaction.channel_id), str(character)])

        cursor.execute(f'UPDATE characters SET {", ".join(set_clauses)} WHERE uid = ? AND channel = ? AND name = ?',
                       values)

        if cursor.rowcount == 0:
            await interaction.response.send_message("找不到符合條件的資料", ephemeral=True)
            print("找不到符合條件的資料，沒有更新任何內容")
        else:
            await interaction.response.send_message("成功更新資料", ephemeral=True)
            print("成功更新資料")
            conn.commit()

        conn.close()

    @app_commands.command(name='刪除角色', description='刪除角色資料')
    @app_commands.autocomplete(character=character_autocomplete)
    @app_commands.describe(confirm="輸入\"confirm\"來確認")
    async def delete_character(self, interaction: discord.Interaction, character: str,
                               confirm: app_commands.Range[str, 7, 7]):

        if not confirm == "confirm":
            await interaction.response.send_message("如要刪除，請在confirm欄位**一字不差**填入`confirm`", ephemeral=True)
            return

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute('DELETE FROM characters WHERE uid = ? AND channel = ? AND name = ?',
                       (str(interaction.user.id), str(interaction.channel_id), str(character),))

        if cursor.rowcount == 0:
            await interaction.response.send_message("找不到符合條件的資料", ephemeral=True)
            print("找不到符合條件的資料，沒有更新任何內容")
        else:
            await interaction.response.send_message("刪除角色成功", ephemeral=True)
            print("成功更新資料")
            conn.commit()

        conn.close()


async def setup(bot):
    db = sqlite3.connect(db_path)
    db.execute('''
        CREATE TABLE IF NOT EXISTS characters (
            uid TEXT NOT NULL,
            channel TEXT NOT NULL,
            name TEXT NOT NULL,
            picture TEXT,
            prefix TEXT NOT NULL,
            UNIQUE(channel, name)
        );
    ''')
    db.execute('''
        CREATE TABLE IF NOT EXISTS webhooks (
            channel TEXT PRIMARY KEY,
            url TEXT NOT NULL
        );
    ''')
    db.close()

    await bot.add_cog(character_wh(bot))
