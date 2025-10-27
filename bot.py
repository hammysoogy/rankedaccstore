import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Button, View
from datetime import datetime
from flask import Flask
from threading import Thread
import os
import re

# ---------------- CONFIG ----------------
TOKEN = os.environ.get("DISCORD_TOKEN")  # Bot token from environment

CHANNEL_ID = 1419693652732805224           # Embed channel
RULES_CHANNEL_ID = 123456789012345678
CATEGORY_ID = 1417817985825116253
TRANSCRIPT_CHANNEL_ID = 1432416214717829242
STOCK_ROLE_ID = 1432421803057348608
STOCK_MESSAGE_CHANNEL_ID = 1415420581675008064  # Channel for stock emoji
STOCK_MESSAGE_ID = 1430171667438637146          # Message ID to update

# ---------------- BOT SETUP ----------------
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

ticket_counter = 0
bot.status_embed_message_id = None
bot.status_emoji = "🟢"

# ------------------ KEEP ALIVE ------------------
app = Flask(__name__)

@app.route("/")
def home():
    return "✅ Bot is alive!"

def _run_flask():
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)

def keep_alive():
    t = Thread(target=_run_flask, daemon=True)
    t.start()

# ---------------- Utility ----------------
async def get_next_ticket_number(guild: discord.Guild):
    global ticket_counter
    category = discord.utils.get(guild.categories, id=CATEGORY_ID)
    if not category:
        return 0
    ticket_channels = [
        c for c in category.text_channels if c.name.startswith("ticket-") and c.name[7:].isdigit()
    ]
    if not ticket_channels:
        ticket_counter = 0
    else:
        numbers = [int(c.name.split("-")[1]) for c in ticket_channels]
        ticket_counter = max(numbers) + 1
    return ticket_counter


async def send_transcript(channel: discord.TextChannel):
    transcript_channel = channel.guild.get_channel(TRANSCRIPT_CHANNEL_ID)
    if not transcript_channel:
        return
    messages = [
        f"[{m.created_at.strftime('%Y-%m-%d %H:%M:%S')}] {m.author}: {m.content}"
        async for m in channel.history(limit=None, oldest_first=True)
    ]
    transcript_text = "\n".join(messages) or "(No messages logged)"
    file = discord.File(fp=bytes(transcript_text, "utf-8"), filename=f"{channel.name}.txt")
    embed = discord.Embed(
        title="📄 Ticket Transcript",
        description=f"Transcript from {channel.mention}",
        color=discord.Color.dark_gray(),
    )
    await transcript_channel.send(embed=embed, file=file)

# ---------------- Ticket Buttons ----------------
class SupportControls(discord.ui.View):
    def __init__(self, channel: discord.TextChannel):
        super().__init__(timeout=None)
        self.channel = channel

    @discord.ui.button(label="Transcript", style=discord.ButtonStyle.secondary, emoji="📄")
    async def transcript(self, interaction: discord.Interaction, button: discord.ui.Button):
        await send_transcript(self.channel)
        await interaction.response.send_message("📄 Transcript sent to logs.", ephemeral=True)

    @discord.ui.button(label="Open", style=discord.ButtonStyle.success, emoji="🔓")
    async def reopen(self, interaction: discord.Interaction, button: discord.ui.Button):
        overwrites = self.channel.overwrites
        overwrites[interaction.user] = discord.PermissionOverwrite(view_channel=True, send_messages=True)
        await self.channel.edit(overwrites=overwrites)
        await interaction.response.send_message("🔓 Ticket reopened.", ephemeral=True)

    @discord.ui.button(label="Delete", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("🗑️ Deleting ticket...", ephemeral=True)
        await send_transcript(self.channel)
        await self.channel.delete()


class CloseButton(discord.ui.View):
    def __init__(self, channel: discord.TextChannel):
        super().__init__(timeout=None)
        self.channel = channel

    @discord.ui.button(label="Close", emoji="🔒", style=discord.ButtonStyle.secondary)
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await send_transcript(self.channel)
        embed = discord.Embed(
            description=f"🔒 Ticket closed by {interaction.user.mention}",
            color=discord.Color.dark_gray(),
        )
        embed.set_author(
            name="Ticket Tool",
            icon_url="https://cdn.discordapp.com/emojis/1201947996109092925.webp?size=96&quality=lossless",
        )
        await interaction.response.send_message(embed=embed, view=SupportControls(self.channel))


# ---------------- Ticket Modal ----------------
class TicketModal(discord.ui.Modal, title="Ranked Enabled Account"):
    quantity = discord.ui.TextInput(
        label="How many level 20 accounts are you buying?",
        placeholder="Enter quantity...",
        required=True,
    )
    payment = discord.ui.TextInput(
        label="Payment method",
        placeholder="Robux, Brainrots, Nitro, etc...",
        required=True,
    )

    async def on_submit(self, interaction: discord.Interaction):
        guild = interaction.guild
        number = await get_next_ticket_number(guild)
        formatted_number = f"{number:03d}"
        category = discord.utils.get(guild.categories, id=CATEGORY_ID)
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, attach_files=True, embed_links=True),
            guild.me: discord.PermissionOverwrite(view_channel=True),
        }
        ticket_channel = await guild.create_text_channel(
            name=f"ticket-{formatted_number}", category=category, overwrites=overwrites, reason="New ticket created"
        )
        embed = discord.Embed(
            description=(
                "Please wait for a response. Do **NOT CLOSE THIS TICKET** or you may be muted.\n"
                f"While you wait, please read <#{RULES_CHANNEL_ID}>."
            ),
            color=discord.Color.dark_gray(),
        )
        embed.set_author(
            name="Ticket Tool",
            icon_url="https://cdn.discordapp.com/emojis/1201947996109092925.webp?size=96&quality=lossless",
        )
        embed.add_field(name="Quantity", value=f"```{self.quantity.value}```", inline=False)
        embed.add_field(name="Payment Method", value=f"```{self.payment.value}```", inline=False)
        await ticket_channel.send(embed=embed, view=CloseButton(ticket_channel))
        await interaction.response.send_message(f"Ticket created: {ticket_channel.mention}", ephemeral=True)


# ---------------- Purchase & Stock Buttons ----------------
class PurchaseButton(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🛒 Purchase", style=discord.ButtonStyle.success)
    async def purchase(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TicketModal())

    @discord.ui.button(label="📦 Check Stock", style=discord.ButtonStyle.secondary)
    async def check_stock(self, interaction: discord.Interaction, button: discord.ui.Button):
        stock_role = interaction.guild.get_role(STOCK_ROLE_ID)
        if stock_role not in interaction.user.roles:
            await interaction.response.send_message("❌ You do not have permission to check stock.", ephemeral=True)
            return
        stock_count = 42
        await interaction.response.send_message(f"📦 Current stock: {stock_count}", ephemeral=True)


# ---------------- /embed Command ----------------
@bot.tree.command(name="embed", description="Send purchase embed (Admin Only)")
@app_commands.checks.has_permissions(administrator=True)
async def embed_command(interaction: discord.Interaction):
    channel = bot.get_channel(CHANNEL_ID)
    if not channel:
        await interaction.response.send_message("❌ Channel not found.", ephemeral=True)
        return

    if bot.status_embed_message_id:
        try:
            old_message = await channel.fetch_message(bot.status_embed_message_id)
            await old_message.delete()
        except:
            pass

    embed = discord.Embed(
        title="",
        description=(
            "**# PAYMENT METHODS**\n"
            f"**# STATUS: {bot.status_emoji}**\n"
            "> <:emoji:1415780267154477147>  **400 Robux**\n"
            "> <:loscomb:1427626337140609034>  **Brainrots 15M/s**\n\n"
            f"Check out <#{RULES_CHANNEL_ID}> to see that we are legit!"
        ),
        color=discord.Color.from_str("#FFA43D"),
    )
    embed.set_author(name="Ranked Enabled Account")
    embed.set_footer(text="thanks for buying!")
    embed.set_image(
        url="https://media.discordapp.net/attachments/1415427200232067186/1432412906284126278/wwdwdq_2_upscayl_4x_high-fidelity-4x_1_1.png?ex=6900f5f9&is=68ffa479&hm=34eb3cffe291e4deb3ac74c37170645cca62d837c849ad433dd6eb36148a289a&=&format=webp&quality=lossless"
    )

    message = await channel.send(embed=embed, view=PurchaseButton())
    bot.status_embed_message_id = message.id
    await interaction.response.send_message("✅ Embed sent successfully!", ephemeral=True)


# ---------------- /status Command ----------------
@bot.tree.command(name="status", description="Change the embed status emoji (Admin Only)")
@app_commands.describe(emoji="The new status emoji (e.g., 🟢, 🟠, 🔴)")
@app_commands.checks.has_permissions(administrator=True)
async def status_command(interaction: discord.Interaction, emoji: str):
    bot.status_emoji = emoji

    channel = bot.get_channel(CHANNEL_ID)
    if channel and bot.status_embed_message_id:
        try:
            old_message = await channel.fetch_message(bot.status_embed_message_id)
            await old_message.delete()
        except:
            pass

        embed = discord.Embed(
            title="",
            description=(
                "**# PAYMENT METHODS**\n"
                f"**# STATUS: {bot.status_emoji}**\n"
                "> <:emoji:1415780267154477147>  **400 Robux**\n"
                "> <:loscomb:1427626337140609034>  **Brainrots 15M/s**\n\n"
                f"Check out <#{RULES_CHANNEL_ID}> to see that we are legit!"
            ),
            color=discord.Color.from_str("#FFA43D"),
        )
        embed.set_author(name="Ranked Enabled Account")
        embed.set_footer(text="thanks for buying!")
        embed.set_image(
            url="https://media.discordapp.net/attachments/1415427200232067186/1432412906284126278/wwdwdq_2_upscayl_4x_high-fidelity-4x_1_1.png?ex=6900f5f9&is=68ffa479&hm=34eb3cffe291e4deb3ac74c37170645cca62d837c849ad433dd6eb36148a289a&=&format=webp&quality=lossless"
        )

        message = await channel.send(embed=embed, view=PurchaseButton())
        bot.status_embed_message_id = message.id

    stock_channel = bot.get_channel(STOCK_MESSAGE_CHANNEL_ID)
    if stock_channel:
        try:
            stock_message = await stock_channel.fetch_message(STOCK_MESSAGE_ID)
            content = stock_message.content
            new_content = re.sub(r"(Stock:)\s*[:\w_]+", f"Stock: {emoji}", content)
            await stock_message.edit(content=new_content)
        except:
            pass

    await interaction.response.send_message(f"✅ Status updated to {emoji}", ephemeral=True)


# ---------------- Error Handling ----------------
@embed_command.error
@status_command.error
async def admin_only_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.errors.MissingPermissions):
        await interaction.response.send_message("❌ You must be an admin to use this command.", ephemeral=True)


# ---------------- on_ready ----------------
@bot.event
async def on_ready():
    await bot.change_presence(
        activity=discord.Activity(type=discord.ActivityType.watching, name="for orders..")
    )
    await bot.tree.sync()
    print(f"✅ Logged in as {bot.user} | Status: Watching for orders..")


# ---------------- RUN BOT ----------------
keep_alive()
bot.run(TOKEN)
