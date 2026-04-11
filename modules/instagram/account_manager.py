from config.settings import get_accounts, TARGET_NICHE
from modules.instagram.bot import InstagramBot
from modules.instagram.comments import CommentHandler
from modules.instagram.stories import StoryHandler


class AccountManager:
    """Gerencia múltiplas contas Instagram — DMs, comentários e stories."""

    def __init__(self):
        self.bots: list[InstagramBot] = []
        self._init_bots()

    def _init_bots(self):
        for account in get_accounts():
            try:
                bot = InstagramBot(account["username"], account["password"])
                self.bots.append(bot)
            except Exception as e:
                print(f"[AccountManager] Falha em @{account['username']}: {e}")
        print(f"[AccountManager] {len(self.bots)} conta(s) ativa(s)")

    def run_campaigns(self, messages_per_account: int = 80) -> int:
        """Envia DMs para leads Apollo com instagram_username."""
        total = 0
        for bot in self.bots:
            sent = bot.run_campaign(limit=messages_per_account)
            total += sent
        print(f"[AccountManager] Total DMs enviados: {total}")
        return total

    def check_replies(self):
        """Verifica e responde DMs — outbound (Apollo) e inbound orgânicos."""
        for bot in self.bots:
            bot.process_replies()

    def monitor_comments(self, posts_limit: int = 5) -> int:
        """
        Monitora comentários nos últimos N posts de cada conta.
        Responde publicamente + envia DM para comentários com sinal de interesse.
        """
        total = 0
        for bot in self.bots:
            handler = CommentHandler(bot.username, bot.client)
            found = handler.monitor_recent_posts(posts_limit=posts_limit)
            total += found
            print(f"[AccountManager] @{bot.username}: {found} comentários processados")
        return total

    def check_new_followers(self, fetch_limit: int = 100) -> int:
        """
        Detecta novos seguidores e os salva no CRM para análise posterior.
        """
        total = 0
        for bot in self.bots:
            from modules.instagram.followers import FollowerMonitor
            monitor = FollowerMonitor(bot.username, bot.client)
            found = monitor.check_new_followers(fetch_limit=fetch_limit)
            total += found
        return total

    def analyze_follower_profiles(self, batch_size: int = 50) -> int:
        """
        Para seguidores ainda não analisados:
        1. Apify scrapes o perfil completo
        2. Claude pontua: hot / warm / cold
        3. Só hot leads ficam com intent_score="high" e serão contatados
        """
        from modules.instagram.followers import FollowerMonitor
        from modules.prospecting.apify_client import ApifyClient

        if not self.bots:
            return 0

        # Usa a primeira conta para buscar a fila de análise
        bot = self.bots[0]
        monitor = FollowerMonitor(bot.username, bot.client)
        pending = monitor.get_pending_analysis(limit=batch_size)

        if not pending:
            print("[AccountManager] Nenhum seguidor pendente de análise")
            return 0

        print(f"[AccountManager] Analisando {len(pending)} seguidores via Apify...")
        apify = ApifyClient()
        analyzed = apify.analyze_follower_batch(pending, niche=TARGET_NICHE)
        return analyzed

    def process_story_replies(self) -> int:
        """
        Processa respostas e reações a stories de cada conta.
        Inicia ou continua qualificação via DM.
        """
        total = 0
        for bot in self.bots:
            handler = StoryHandler(bot.username, bot.client)
            processed = handler.process_story_replies()
            total += processed
        return total
