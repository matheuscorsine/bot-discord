import discord
from discord.ext import commands, tasks
import asyncio
import re
from datetime import datetime, timedelta, timezone
import random

from core.database import (
    add_giveaway, remove_giveaway, add_giveaway_participant,
    get_giveaway_participants, get_finished_giveaways
)

# Função para converter tempo como "10m", "1h", "2d" para um objeto timedelta
def parse_duration(duration_str: str) -> timedelta:
    match = re.match(r"(\d+)([smhd])", duration_str.lower())
    if not match:
        raise ValueError("Formato de tempo inválido. Use 's', 'm', 'h' ou 'd'.")
    
    value, unit = int(match.group(1)), match.group(2)
    if unit == 's':
        return timedelta(seconds=value)
    if unit == 'm':
        return timedelta(minutes=value)
    if unit == 'h':
        return timedelta(hours=value)
    if unit == 'd':
        return timedelta(days=value)

class GiveawayView(discord.ui.View):
    def __init__(self, required_roles: list[int]):
        super().__init__(timeout=None)
        self.required_roles = set(required_roles)

    @discord.ui.button(label="🎉 Participar", style=discord.ButtonStyle.primary, custom_id="giveaway_entry_button")
    async def entry_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Verifica se o membro tem os cargos necessários
        member_roles = {role.id for role in interaction.user.roles}
        if self.required_roles and not self.required_roles.issubset(member_roles):
            # Monta a mensagem de erro com os cargos que faltam
            missing_roles_mentions = [f"<@&{role_id}>" for role_id in self.required_roles if role_id not in member_roles]
            await interaction.response.send_message(
                f"❌ Você não pode entrar neste sorteio. Requisitos: {' '.join(missing_roles_mentions)}",
                ephemeral=True
            )
            return

        # Adiciona o participante ao banco de dados
        await add_giveaway_participant(interaction.message.id, interaction.user.id)
        
        # Atualiza a contagem de participantes no embed
        participants = await get_giveaway_participants(interaction.message.id)
        embed = interaction.message.embeds[0]
        embed.set_field_at(1, name="Participantes", value=f"**{len(participants)}**", inline=True)
        
        await interaction.message.edit(embed=embed)
        await interaction.response.send_message("✅ Você entrou no sorteio!", ephemeral=True)

class GiveawayCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.giveaway_end_checker.start()

    def cog_unload(self):
        self.giveaway_end_checker.cancel()

    @commands.has_permissions(administrator=True)
    @commands.command(name="gsortear", aliases=["gcreate"])
    async def create_giveaway_cmd(self, ctx, duration: str, winners: int, *, prize_and_roles: str):
        """Inicia um sorteio. Ex: !gsortear 10m 1 "Prêmio do Sorteio" @cargo1 @cargo2"""
        try:
            delta = parse_duration(duration)
        except ValueError as e:
            await ctx.reply(f"Erro no formato de tempo: {e}", mention_author=True)
            return

        if winners < 1:
            await ctx.reply("O número de vencedores deve ser pelo menos 1.", mention_author=True)
            return

        # Separa o prêmio dos cargos
        parts = prize_and_roles.split()
        prize_words = []
        required_roles = []
        for part in parts:
            if part.startswith("<@&"): # É uma menção de cargo
                try:
                    role_id = int(part.strip("<@&>"))
                    required_roles.append(role_id)
                except ValueError:
                    continue # Ignora menções inválidas
            else:
                prize_words.append(part)
        
        prize = " ".join(prize_words)
        if not prize:
            await ctx.reply("Você precisa especificar um prêmio para o sorteio.", mention_author=True)
            return

        end_time = datetime.now(timezone.utc) + delta
        required_roles_csv = ",".join(map(str, required_roles)) if required_roles else None

        embed = discord.Embed(
            title=f"🎉 SORTEIO: {prize}",
            description=f"Reaja com 🎉 para entrar!\nTermina em: <t:{int(end_time.timestamp())}:R> (<t:{int(end_time.timestamp())}:f>)",
            color=discord.Color.gold()
        )
        embed.add_field(name="Vencedores", value=f"**{winners}**", inline=True)
        embed.add_field(name="Participantes", value="**0**", inline=True)
        
        if required_roles:
            role_mentions = " ".join([f"<@&{role_id}>" for role_id in required_roles])
            embed.add_field(name="Requisitos", value=f"Apenas para membros com o(s) cargo(s): {role_mentions}", inline=False)

        embed.set_footer(text=f"Sorteio iniciado por {ctx.author.display_name}")

        view = GiveawayView(required_roles)
        giveaway_message = await ctx.send(embed=embed, view=view)

        await add_giveaway(giveaway_message.id, ctx.guild.id, ctx.channel.id, end_time, winners, prize, required_roles_csv)
        # Apaga o comando original para manter o chat limpo
        await ctx.message.delete()

    @tasks.loop(seconds=15)
    async def giveaway_end_checker(self):
        finished_giveaways = await get_finished_giveaways()
        for g in finished_giveaways:
            message_id, guild_id, channel_id, end_time_str, winner_count, prize, roles_csv = g
            
            guild = self.bot.get_guild(guild_id)
            if not guild:
                await remove_giveaway(message_id)
                continue

            channel = guild.get_channel(channel_id)
            if not channel:
                await remove_giveaway(message_id)
                continue

            try:
                message = await channel.fetch_message(message_id)
            except discord.NotFound:
                await remove_giveaway(message_id)
                continue
            
            participants = await get_giveaway_participants(message_id)
            
            winners = []
            if participants:
                # Sorteia os vencedores
                winner_ids = random.sample(participants, min(winner_count, len(participants)))
                winners = [f"<@{user_id}>" for user_id in winner_ids]

            # Edita a mensagem original do sorteio
            end_time_obj = datetime.fromisoformat(end_time_str)
            embed = message.embeds[0]
            embed.color = discord.Color.dark_red()
            embed.description = f"Sorteio finalizado em <t:{int(end_time_obj.timestamp())}:f>"
            
            if not winners:
                result_description = "Não houve participantes suficientes!"
            else:
                result_description = f"**Vencedor(es):** {', '.join(winners)}"

            embed.add_field(name="Resultado", value=result_description, inline=False)

            # Desativa o botão de participar
            view = discord.ui.View.from_message(message)
            entry_button = discord.utils.get(view.children, custom_id="giveaway_entry_button")
            if entry_button:
                entry_button.disabled = True
            
            await message.edit(embed=embed, view=view)

            # Envia uma nova mensagem anunciando os vencedores
            await message.reply(f"🎉 O sorteio de **{prize}** acabou! Parabéns {', '.join(winners)}!")

            # Remove o sorteio do banco de dados de "ativos"
            await remove_giveaway(message_id)

    @giveaway_end_checker.before_loop
    async def before_checker(self):
        await self.bot.wait_until_ready()

# Função obrigatória para carregar o Cog
async def setup(bot):
    await bot.add_cog(GiveawayCommands(bot))