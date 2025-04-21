import discord
import os
import random
import sys
import asyncio
import datetime
from discord.commands import SlashCommandGroup # For grouping if needed later
from discord.ext import commands # Still potentially useful, keep import
from dotenv import load_dotenv

# --- Configuration ---
load_dotenv()
DISCORD_TOKEN = os.getenv('DISCORD_BOT_TOKEN')

if not DISCORD_TOKEN:
    print("CRITICAL ERROR: DISCORD_BOT_TOKEN environment variable not found.")
    sys.exit("Bot token is missing. Please set the DISCORD_BOT_TOKEN environment variable.")

# --- Intents Setup ---
intents = discord.Intents.default()
intents.message_content = True # Needed to read mentions if check changes later
intents.members = True         # To list members in channel
intents.presences = True       # To check if members are online/idle/dnd
# Message history is needed for the delete command
intents.messages = True # Redundant with default usually, but explicit

# Use discord.Bot
bot = discord.Bot(intents=intents)

# --- Global Variable ---
bot_owner_id = None # Will be set in on_ready

# --- Helper Functions ---
async def check_delete_perms(interaction: discord.Interaction):
    """Checks if user is owner or has Manage Messages permission."""
    if not interaction.guild: # Command must be used in a server
        # Check if response already sent before sending error (e.g. if check is called after defer)
        if not interaction.response.is_done():
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
        else:
            await interaction.followup.send("This command can only be used in a server.", ephemeral=True)
        return False

    # Ensure owner ID is loaded
    global bot_owner_id
    if bot_owner_id is None:
        try:
            app_info = await bot.application_info()
            bot_owner_id = app_info.owner.id
            print(f"(Re-fetched Owner ID for perm check: {bot_owner_id})")
        except Exception as e:
            print(f"!!! ERROR: Could not verify owner ID during perm check: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message("Error: Could not verify owner ID for permissions check.", ephemeral=True)
            else:
                await interaction.followup.send("Error: Could not verify owner ID for permissions check.", ephemeral=True)
            return False

    # Check if invoker is the bot owner
    if interaction.user.id == bot_owner_id:
        return True

    # Check if invoker has 'Manage Messages' permission in the server
    # Use guild_permissions as interaction might not have member context initially in some cases
    if interaction.user.guild_permissions.manage_messages:
        return True

    # If neither, deny permission
    if not interaction.response.is_done():
        await interaction.response.send_message("You need the 'Manage Messages' permission or be the bot owner to use this command.", ephemeral=True)
    else:
        await interaction.followup.send("You need the 'Manage Messages' permission or be the bot owner to use this command.", ephemeral=True)
    return False


# --- Events ---
@bot.event
async def on_ready():
    """Runs once when the bot connects and is ready."""
    global bot_owner_id
    # Clear previous owner ID in case of reconnect/reload
    bot_owner_id = None
    print(f'Logged in as {bot.user.name} ({bot.user.id})')
    print(f'Library Version: {discord.__version__}')
    print('Fetching owner information...')
    try:
        app_info = await bot.application_info()
        bot_owner_id = app_info.owner.id
        print(f"Successfully fetched Owner ID: {bot_owner_id} ({app_info.owner.name})")
    except Exception as e:
        print(f"!!! WARNING: Could not fetch owner ID: {e}")
        print("!!! The /shutdownserver and /delete_pings owner checks may not work correctly initially.")

    print('Bot is ready and listening for mentions!')
    print('------')

    # Using Custom Activity
    custom_activity = discord.CustomActivity(
        name="I'm probably broken...",  # Your custom text here
        emoji="😱"                # Your emoji here (Unicode works directly)
    )
    await bot.change_presence(status=discord.Status.idle, activity=custom_activity) # Set custom activity here

@bot.event
async def on_message(message: discord.Message):
    """Handles messages sent in channels the bot can see."""

    # 1. Ignore messages from bots (including self)
    if message.author.bot:
        return

    # 2. Check if the bot itself was mentioned
    if bot.user in message.mentions:

        print(f"Bot mentioned by {message.author} in #{message.channel.name} (Server: {message.guild.name})")

        # 3. Ensure it's in a server text channel (not a DM)
        if not message.guild or not isinstance(message.channel, discord.TextChannel):
            print(f"Ignoring bot mention from DM or non-text channel by {message.author}")
            return

        # 4. Get potential members to mention (excluding the bot and the author)
        eligible_members = []
        try:
            for member in message.channel.members:
                if (not member.bot and
                    member != message.author and
                    member.status in [discord.Status.online, discord.Status.idle, discord.Status.dnd, discord.Status.offline]):
                    eligible_members.append(member)
        except Exception as e:
            print(f"Error retrieving members in '{message.channel.name}': {e}")
            try:
                await message.reply(f"Sorry {message.author.mention}, I had trouble getting the member list for this channel.", mention_author=False, delete_after=15)
            except discord.Forbidden: pass
            return

        # 5. If eligible members exist, send reply in main channel
        if eligible_members:
            chosen_member = random.choice(eligible_members)
            reply_content = f"{chosen_member.mention}" # Just the ping
            try:
                # Reply to the original message, DO NOT ping the original author.
                await message.reply(reply_content, mention_author=False)
                print(f"Replied to mention from {message.author}. Pinged: {chosen_member}")
            except discord.Forbidden:
                print(f"ERROR: Missing permissions to send reply in #{message.channel.name} on server '{message.guild.name}'")
                try:
                    await message.channel.send(f"Sorry {message.author.mention}, I couldn't reply here (missing permissions).", delete_after=15)
                except discord.Forbidden: pass
            except Exception as e:
                print(f"ERROR: Failed to send mention reply: {e}")
        else:
            # No eligible members found
            print(f"No eligible online users found to ping for mention by {message.author} in #{message.channel.name}")
            try:
                 await message.reply(f"Sorry {message.author.mention}, couldn't find anyone online and eligible to ping right now!", mention_author=False, delete_after=15)
            except discord.Forbidden:
                 print(f"ERROR: Missing permissions to send 'not found' reply in #{message.channel.name}")
            except Exception as e:
                 print(f"ERROR: Failed to send 'not found' reply: {e}")


# --- Slash Commands ---

@bot.slash_command(name="delete_pings", description="[Owner/Manage Messages] Deletes all messages sent by this bot in this server.")
async def delete_pings(interaction: discord.Interaction):
    """Deletes all messages sent by the bot in the current guild."""
    print(f"'/delete_pings' invoked by {interaction.user} ({interaction.user.id}) in server '{interaction.guild.name}' ({interaction.guild.id})")

    # Defer response first, before permission check, as check might take time if owner ID needs fetching
    await interaction.response.defer(ephemeral=True)
    print("Interaction deferred.")

    # 1. Check Permissions (Owner or Manage Messages)
    if not await check_delete_perms(interaction):
        # check_delete_perms sends the denial message via followup now
        print("Permission check failed for /delete_pings.")
        return

    # 2. Initialize counters
    deleted_count = 0
    failed_count = 0
    start_time = datetime.datetime.now(datetime.timezone.utc)
    fourteen_days_ago = start_time - datetime.timedelta(days=14)

    # 3. Iterate through all text channels the bot can see
    print(f"Starting message deletion scan in server '{interaction.guild.name}'...")
    if not interaction.guild: # Should be caught by check_delete_perms, but safety check
        await interaction.followup.send("Error: Guild context lost.", ephemeral=True)
        return

    for channel in interaction.guild.text_channels:
        # Reset lists for each channel
        messages_to_delete_bulk = []
        messages_to_delete_single = []
        channel_deleted_count = 0
        channel_failed_count = 0
        processed_count = 0 # Counter for progress logging

        print(f"Scanning channel: #{channel.name} ({channel.id})")
        try:
            # Check if bot has Read Message History and Manage Messages in *this specific channel*
            # Use guild.me as interaction.guild.me might not be available if context is lost somehow
            bot_member = interaction.guild.get_member(bot.user.id)
            if not bot_member:
                 print(f"Skipping channel #{channel.name} - Could not get bot member object.")
                 continue
            bot_perms = channel.permissions_for(bot_member)
            if not bot_perms.read_message_history or not bot_perms.manage_messages:
                print(f"Skipping channel #{channel.name} - Missing Read History or Manage Messages permission.")
                continue

            # --- !!! MEMORY SAFE HISTORY ITERATION START !!! ---
            # Iterate through history more carefully, fetching in chunks implicitly
            # No limit=None to avoid loading everything into memory
            async for message in channel.history(limit=5000): # Process history (adjust limit if needed, None IS dangerous)
                processed_count += 1
                if processed_count % 500 == 0: # Log progress occasionally
                    print(f"  [#{channel.name}] Scanned {processed_count} messages...")

                # Check if message is from the bot
                if message.author.id == bot.user.id: # Safer check using ID
                    if message.created_at > fourteen_days_ago:
                        messages_to_delete_bulk.append(message)
                    else:
                        messages_to_delete_single.append(message)

                    # --- Process deletes periodically to avoid large lists in memory ---
                    if len(messages_to_delete_bulk) >= 99: # Keep slightly under 100 limit just in case
                         try:
                            await channel.delete_messages(messages_to_delete_bulk)
                            print(f"  [#{channel.name}] Bulk deleted {len(messages_to_delete_bulk)} messages.")
                            deleted_count += len(messages_to_delete_bulk)
                            channel_deleted_count += len(messages_to_delete_bulk)
                            messages_to_delete_bulk = [] # Clear the list
                            await asyncio.sleep(1) # Sleep after bulk delete
                         except discord.Forbidden:
                             print(f"  [#{channel.name}] ERROR: Permission denied during periodic bulk delete. Adding to single queue.")
                             messages_to_delete_single.extend(messages_to_delete_bulk)
                             messages_to_delete_bulk = []
                         except discord.HTTPException as bulk_e:
                             print(f"  [#{channel.name}] Error bulk deleting chunk: {bulk_e}. Adding to single delete queue.")
                             messages_to_delete_single.extend(messages_to_delete_bulk)
                             messages_to_delete_bulk = [] # Still clear list
                         except Exception as e:
                             print(f"  [#{channel.name}] Unexpected error during periodic bulk delete: {e}. Adding to single queue.")
                             messages_to_delete_single.extend(messages_to_delete_bulk)
                             messages_to_delete_bulk = []


            print(f"  [#{channel.name}] Finished initial history scan ({processed_count} messages). Processing remaining deletes...")
            # --- !!! MEMORY SAFE HISTORY ITERATION END !!! ---


            # --- Process remaining messages (bulk < 14d, single > 14d or failed) ---
            # Bulk delete any remaining messages younger than 14 days
            if messages_to_delete_bulk:
                 # Split into chunks of 100
                 for i in range(0, len(messages_to_delete_bulk), 99): # Use 99 again
                    chunk = messages_to_delete_bulk[i:i+99]
                    if chunk:
                        try:
                            await channel.delete_messages(chunk)
                            deleted_count += len(chunk)
                            channel_deleted_count += len(chunk)
                            print(f"  [#{channel.name}] Bulk deleted remaining {len(chunk)} messages")
                            await asyncio.sleep(1)
                        except discord.Forbidden:
                             print(f"  [#{channel.name}] ERROR: Permission denied during final bulk delete. Skipping chunk.")
                             failed_count += len(chunk); channel_failed_count += len(chunk)
                        except discord.HTTPException as e:
                            print(f"  [#{channel.name}] Failed to bulk delete remaining chunk: {e}. Trying single delete.")
                            messages_to_delete_single.extend(chunk) # Add failed ones to single delete
                        except Exception as e:
                            print(f"  [#{channel.name}] Unexpected error during final bulk delete: {e}. Trying single delete.")
                            messages_to_delete_single.extend(chunk)


            # Delete messages older than 14 days (or failed bulk ones) one by one
            print(f"  [#{channel.name}] Processing {len(messages_to_delete_single)} messages for single delete...")
            for msg_to_delete in messages_to_delete_single:
                try:
                    await msg_to_delete.delete()
                    deleted_count += 1
                    channel_deleted_count += 1
                    await asyncio.sleep(1.5) # Sleep between single deletes
                except discord.Forbidden:
                    print(f"  [#{channel.name}] Failed single delete {msg_to_delete.id} (Forbidden).")
                    failed_count += 1; channel_failed_count += 1
                except discord.NotFound:
                    print(f"  [#{channel.name}] Failed single delete {msg_to_delete.id} (NotFound).")
                except discord.HTTPException as e:
                    print(f"  [#{channel.name}] Failed single delete {msg_to_delete.id} (HTTPException: {e}).")
                    failed_count += 1; channel_failed_count += 1
                    await asyncio.sleep(5) # Back off longer
                except Exception as e:
                     print(f"  [#{channel.name}] Unexpected error during single delete {msg_to_delete.id}: {e}")
                     failed_count += 1; channel_failed_count += 1


        except discord.Forbidden:
            print(f"Skipping channel #{channel.name} - Permission denied accessing history.")
        except Exception as e:
            print(f"An unexpected error occurred processing channel #{channel.name}: {e}")
            import traceback
            traceback.print_exc() # Print full traceback for unexpected errors

        if channel_deleted_count > 0 or channel_failed_count > 0:
             print(f"Finished channel #{channel.name}: Deleted={channel_deleted_count}, Failed={channel_failed_count}")

    # 5. Send final report
    duration = datetime.datetime.now(datetime.timezone.utc) - start_time
    print(f"Deletion process completed in {duration}. Total Deleted: {deleted_count}, Total Failed: {failed_count}")
    try:
        await interaction.followup.send(f"Deletion scan complete!\nDeleted approx: {deleted_count} messages.\nFailed/Skipped approx: {failed_count} messages.\nTime taken: {duration}", ephemeral=True)
    except Exception as followup_e:
        print(f"Error sending followup message: {followup_e}")


@bot.slash_command(name="shutdownserver", description="[Owner Only] Shuts down the bot process.")
async def shutdown_command(interaction: discord.Interaction):
    """Handles the /shutdownserver command."""
    # Add a print statement right at the start to confirm entry
    print(f"'/shutdownserver' command received from {interaction.user} ({interaction.user.id})")

    global bot_owner_id

    # Defer might be needed if owner check takes time, but usually isn't. Send immediate response if possible.
    # await interaction.response.defer(ephemeral=True) # Generally avoid deferring here unless needed

    # Double check owner ID if it failed on_ready
    if bot_owner_id is None:
        print("Owner ID is None, attempting to fetch...")
        try:
            app_info = await bot.application_info()
            bot_owner_id = app_info.owner.id
            print(f"(Re-fetched Owner ID: {bot_owner_id})")
        except Exception as e:
            print(f"!!! FATAL: Could not verify owner ID during shutdown command: {e}")
            if not interaction.response.is_done():
                 await interaction.response.send_message(
                    "Error: Could not verify owner ID. Shutdown cannot proceed safely.", ephemeral=True
                 )
            else:
                 await interaction.followup.send("Error: Could not verify owner ID. Shutdown cannot proceed safely.", ephemeral=True)
            return

    # Check if the user invoking is the bot owner
    if interaction.user.id == bot_owner_id:
        print("Shutdown authorized by owner.")
        # Respond before shutting down
        if not interaction.response.is_done():
            await interaction.response.send_message("Acknowledged. Shutting down the bot process...", ephemeral=True)
        else:
             # Should generally not be deferred, but handle just in case
             await interaction.followup.send("Acknowledged. Shutting down the bot process...", ephemeral=True)


        print("Closing connection and exiting script...")
        await asyncio.sleep(1) # Give message time to send
        await bot.close()
        # sys.exit might not be the best way if run under certain managers,
        # letting bot.close() finish and the script end naturally is often better.
        # sys.exit("Bot shutdown initiated by owner via /shutdownserver command.")
        print("Bot run loop should exit now.") # Let the main loop handle exit
    else:
        print(f"Unauthorized shutdown attempt by {interaction.user}.")
        if not interaction.response.is_done():
             await interaction.response.send_message("Error: You do not have permission to use this command.", ephemeral=True)
        else:
             await interaction.followup.send("Error: You do not have permission to use this command.", ephemeral=True)


# --- Error Handling ---
@bot.event
async def on_application_command_error(interaction: discord.Interaction, error: discord.DiscordException):
    """Basic error handler for slash commands."""
    error_message = f"An error occurred with command '{interaction.command.name}': {error}"
    print(f"ERROR: {error_message}")
    import traceback
    traceback.print_exc() # Print full traceback for debugging

    # Check specific errors if needed, e.g., CheckFailure for permission decorators
    # Check if CheckFailure is part of discord.app_commands or discord.ext.commands
    if isinstance(error, commands.CheckFailure) or isinstance(error, discord.app_commands.CheckFailure):
         err_msg = "You do not have the necessary permissions for this command."
    # Handle InteractionResponded separately if possible
    elif isinstance(error, discord.InteractionResponded):
         print("Interaction already responded to, attempting followup for error.")
         err_msg = "Something went wrong, and I might have already responded."
         try:
             await interaction.followup.send(err_msg, ephemeral=True)
         except Exception as followup_e:
             print(f"Failed to send followup error message: {followup_e}")
         return # Stop further processing for this specific error
    else:
         err_msg = "Sorry, something went wrong processing that command."

    if interaction.response.is_done():
        # Use followup if already responded or deferred
        try:
            await interaction.followup.send(err_msg, ephemeral=True)
        except Exception as followup_e:
             print(f"Failed to send followup error message after check: {followup_e}")
    else:
        # Use send_message if not responded yet
        try:
            await interaction.response.send_message(err_msg, ephemeral=True)
        except discord.InteractionResponded: # Catch race condition
             print("Interaction responded before error message could be sent, attempting followup.")
             try:
                 await interaction.followup.send(err_msg, ephemeral=True)
             except Exception as followup_e:
                 print(f"Failed to send followup error message after race condition: {followup_e}")
        except Exception as send_e:
             print(f"Further error sending initial error response: {send_e}")


# --- Run the Bot ---
if __name__ == "__main__":
    print("Attempting to start bot...")
    try:
        bot.run(DISCORD_TOKEN)
    except discord.errors.LoginFailure: # Use specific error type for your library (discord.py or py-cord)
        print("CRITICAL ERROR: Invalid bot token provided.")
    except discord.errors.PrivilegedIntentsRequired as e: # Use specific error type for your library
        print(f"CRITICAL ERROR: Missing required privileged intents: {e}")
    except Exception as e:
        print(f"CRITICAL ERROR during bot startup or runtime: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # This runs when bot.run() finishes (e.g., after bot.close())
        print("Bot process has concluded.")