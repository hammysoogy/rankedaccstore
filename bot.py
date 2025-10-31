import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Button, View
from datetime import datetime
from flask import Flask
from threading import Thread
import os

# ---------------- CONFIG ----------------
TOKEN = os.getenv("DISCORD_TOKEN")

CHANNEL_ID = 1419693652732805224
RULES_CHANNEL_ID = 1416158383039320117
CATEGORY_ID = 1417817985825116253
TRANSCRIPT_CHANNEL_ID = 1432416214717829242
STOCK_ROLE_ID = 1432421803057348608
STOCK_MESSAGE_CHANNEL_ID = 1415420581675008064
STOCK_MESSAGE_ID = 1430171667438637146
INFO_CHANNEL_ID = 1433003641681477644
REACTION_CHANNEL_ID = 1416158383039320117

# ---------------- BOT SETUP ----------------
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.guilds = True
bot = commands.Bot(command_prefix="!", intents=intents)

bot.status_emoji = "🟢"
bot.status_embed_message_id = None
ticket_counter = 0

# ---------------- KEEP ALIVE ----------------
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

# ---------------- UTILITIES ----------------
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

# ---------------- VIEWS ----------------
class SupportControls(View):
    def __init__(self, channel: discord.TextChannel):
        super().__init__(timeout=None)
        self.channel = channel

    @discord.ui.button(label="Transcript", style=discord.ButtonStyle.secondary, emoji="📄")
    async def transcript(self, interaction: discord.Interaction, button: discord.ui.Button):
        await send_transcript(self.channel)
        await interaction.response.send_message("📄 Transcript sent to logs.", ephemeral=True)

    @discord.ui.button(label="Reopen", style=discord.ButtonStyle.success, emoji="🔓")
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

class CloseButton(View):
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
        embed.set_author(name="Ticket Tool")
        await interaction.response.send_message(embed=embed, view=SupportControls(self.channel))

class TicketModal(discord.ui.Modal, title="Ranked Enabled Account"):
    quantity = discord.ui.TextInput(label="How many accounts?", required=True)
    payment = discord.ui.TextInput(label="Payment method", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        guild = interaction.guild
        number = await get_next_ticket_number(guild)
        formatted_number = f"{number:03d}"
        category = discord.utils.get(guild.categories, id=CATEGORY_ID)
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(view_channel=True),
        }
        ticket_channel = await guild.create_text_channel(
            name=f"ticket-{formatted_number}", category=category, overwrites=overwrites
        )
        embed = discord.Embed(
            description=f"Please wait for a response. Read <#{RULES_CHANNEL_ID}> while waiting.",
            color=discord.Color.dark_gray(),
        )
        embed.add_field(name="Quantity", value=f"```{self.quantity.value}```", inline=False)
        embed.add_field(name="Payment", value=f"```{self.payment.value}```", inline=False)
        await ticket_channel.send(embed=embed, view=CloseButton(ticket_channel))
        await interaction.response.send_message(f"✅ Ticket created: {ticket_channel.mention}", ephemeral=True)

class PurchaseButton(View):
    def __init__(self):
        super().__init__(timeout=None)
        info_button = Button(
            label="❓ Info",
            style=discord.ButtonStyle.link,
            url=f"https://discord.com/channels/1415420581675008064/{INFO_CHANNEL_ID}"
        )
        self.add_item(info_button)

    @discord.ui.button(label="🛒 Purchase", style=discord.ButtonStyle.success)
    async def purchase(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TicketModal())

    @discord.ui.button(label="📦 Check Stock", style=discord.ButtonStyle.secondary)
    async def check_stock(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(f"📦 Current stock: {bot.status_emoji}", ephemeral=True)

# ---------------- COMMANDS ----------------
@bot.tree.command(name="embed", description="Post the payment embed with purchase buttons")
@app_commands.checks.has_permissions(administrator=True)
async def embed_command(interaction: discord.Interaction):
    await update_embed(interaction, send_message=True)

@bot.tree.command(name="changestock", description="Change the stock emoji (visible to everyone)")
async def changestock(interaction: discord.Interaction, emoji: str):
    bot.status_emoji = emoji
    await update_embed(interaction)
    await interaction.response.send_message(f"✅ Stock emoji updated to {emoji}!", ephemeral=False)

@bot.tree.command(name="update", description="Refresh the payment embed manually")
@app_commands.checks.has_permissions(administrator=True)
async def update_command(interaction: discord.Interaction):
    await update_embed(interaction)
    await interaction.response.send_message("✅ Embed updated successfully!", ephemeral=True)

async def update_embed(interaction: discord.Interaction, send_message: bool = False):
    channel = bot.get_channel(CHANNEL_ID)
    if not channel:
        return

    # Delete old embed if exists
    if bot.status_embed_message_id:
        try:
            old_message = await channel.fetch_message(bot.status_embed_message_id)
            await old_message.delete()
        except:
            pass

    embed = discord.Embed(
        description=(
            "**# PAYMENT METHODS**\n"
            f"**# STATUS: {bot.status_emoji}**\n"
            "> <:emoji:1415780267154477147>  **400 Robux**\n"
            "> <:loscomb:1427626337140609034>  **~~Brainrots 15M/s~~** (offsale for now)\n\n"
            f"Check out <#{RULES_CHANNEL_ID}> to see that we’re legit!"
        ),
        color=discord.Color.from_str("#FFA43D"),
    )
    embed.set_author(name="Ranked Enabled Account")
    embed.set_image(
        url="https://media.discordapp.net/attachments/1415427200232067186/1432412906284126278/wwdwdq_2_upscayl_4x_high-fidelity-4x_1_1.png?ex=6902f039&is=69019eb9&hm=9f6330f6995a97d1150e6baef00d4baa087b2ee5c66e5a8a64fc3a41ea6cb43e&=&format=webp&quality=lossless"
    )
    embed.set_footer(text="Thanks for buying!")

    message = await channel.send(embed=embed, view=PurchaseButton())
    bot.status_embed_message_id = message.id

# ---------------- AUTO ✅ REACT ----------------
@bot.event
async def on_message(message):
    if message.channel.id == REACTION_CHANNEL_ID and not message.author.bot:
        try:
            await message.add_reaction("✅")
        except:
            pass
    await bot.process_commands(message)

# ---------------- READY EVENT ----------------
@bot.event
async def on_ready():
    await bot.tree.sync()
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="for orders.."))
    print(f"✅ Logged in as {bot.user}")

# ---------------- RUN ----------------
keep_alive()
bot.run(TOKEN)
