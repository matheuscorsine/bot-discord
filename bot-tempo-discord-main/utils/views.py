# Caminho: utils/views.py

import discord
import asyncio

# Importa a função que gera a imagem do ranking
from .image_generator import gerar_leaderboard_card

class RankingView(discord.ui.View):
    """
    View customizada com botões para navegação entre as páginas do ranking.
    """
    def __init__(self, ctx, rows, total_pages):
        super().__init__(timeout=180.0) # A view expira após 180 segundos de inatividade
        self.ctx = ctx
        self.rows = rows
        self.page = 1
        self.total_pages = total_pages
        self.message = None # Armazena a mensagem onde a view está para poder editá-la
        self.update_buttons()

    def update_buttons(self):
        """Atualiza o estado dos botões (ativado/desativado) e o rótulo da página."""
        # O primeiro botão (índice 0) é o 'anterior', desativado na primeira página
        self.children[0].disabled = self.page == 1
        # O terceiro botão (índice 2) é o 'próximo', desativado na última página
        self.children[2].disabled = self.page == self.total_pages
        # O botão do meio (índice 1) é o display, que mostra a página atual
        self.children[1].label = f"{self.page} / {self.total_pages}"

    async def update_message(self, interaction: discord.Interaction):
        """Gera a nova imagem do ranking e atualiza a mensagem original."""
        loop = asyncio.get_running_loop()
        # Executa a geração de imagem (que é síncrona e pode bloquear) em um executor
        # para não travar o bot.
        buf = await loop.run_in_executor(None, gerar_leaderboard_card, self.rows, self.ctx.guild, self.page)
        f = discord.File(fp=buf, filename=f"ranking_pagina_{self.page}.png")
        # Edita a mensagem da interação com a nova imagem e a view atualizada
        await interaction.response.edit_message(attachments=[f], view=self)

    # Decorator que define o botão da esquerda
    @discord.ui.button(emoji="⬅️", style=discord.ButtonStyle.blurple)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Callback executado quando o botão 'anterior' é clicado."""
        if self.page > 1:
            self.page -= 1
            self.update_buttons()
            await self.update_message(interaction)

    # Decorator que define o botão do meio (apenas display)
    @discord.ui.button(label="1 / 1", style=discord.ButtonStyle.grey, disabled=True)
    async def page_display(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Este botão serve apenas para exibir a página, não tem ação."""
        pass

    # Decorator que define o botão da direita
    @discord.ui.button(emoji="➡️", style=discord.ButtonStyle.blurple)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Callback executado quando o botão 'próximo' é clicado."""
        if self.page < self.total_pages:
            self.page += 1
            self.update_buttons()
            await self.update_message(interaction)
            
    async def on_timeout(self):
        """Função chamada quando a view expira (após 180s)."""
        # Desativa todos os botões para o usuário saber que não pode mais interagir
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                # Tenta editar a mensagem original para mostrar os botões desativados
                await self.message.edit(view=self)
            except discord.errors.NotFound:
                # Se a mensagem original foi deletada, ignora o erro
                pass