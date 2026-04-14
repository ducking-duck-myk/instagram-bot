import time
from src.utils import log, random_delay
from src.state_manager import StateManager
from src.retry_handler import RetryHandler, BotFatalError
from src.validator import Validator
from src.anti_duplicate import AntiDuplicate


class BotActions:
    """
    All Instagram actions:
    Follow | Like | Unfollow
    Every action has:
    - Daily limit check
    - Validation
    - Blacklist check
    - Anti-duplication check
    - Smart retry
    - Counter increment only on success
    """

    def __init__(
        self,
        client,
        config:        dict,
        state_manager: StateManager
    ):
        self.client  = client
        self.config  = config
        self.state   = state_manager
        self.retry   = RetryHandler(state_manager)
        self.dupes   = AntiDuplicate()
        self.session_stats = {
            "followed":   0,
            "liked":      0,
            "unfollowed": 0,
            "skipped":    0,
            "errors":     0
        }

    # ─────────────────────────────────────────
    # HELPERS
    # ─────────────────────────────────────────

    def _fetch_medias(self, hashtag: str, limit: int) -> list:
        """Fetch hashtag posts with retry. Returns [] on failure."""
        medias, ok = self.retry.execute(
            self.client.hashtag_medias_recent,
            hashtag,
            amount=limit,
            max_attempts=3,
            action_name=f"fetch #{hashtag}"
        )
        if not ok or medias is None:
            return []
        return medias

    def _record_error(self, msg: str):
        self.session_stats["errors"] += 1
        self.state.increment("errors")
        log(f"❌ {msg}", "ERROR")

    # ─────────────────────────────────────────
    # FOLLOW BY HASHTAG
    # ─────────────────────────────────────────

    def follow_by_hashtag(self, hashtag: str) -> int:
        # Validate
        ok, err = Validator.validate_hashtag(hashtag)
        if not ok:
            log(f"❌ Bad hashtag '{hashtag}': {err}", "ERROR")
            return 0

        # Limit check
        if not self.state.can_follow():
            return 0

        hashtag = hashtag.lstrip("#").strip()
        log(f"🔍 Follow via #{hashtag}", "ACTION")
        self.dupes.mark_hashtag_used(hashtag)

        limit         = self.config["limits"]["hashtag_posts_to_fetch"]
        session_limit = self.config["limits"]["follow_per_session"]
        followed      = 0

        medias = self._fetch_medias(hashtag, limit)
        if not medias:
            log(f"⚠️ No posts for #{hashtag}", "WARNING")
            return 0

        log(f"📱 {len(medias)} posts", "INFO")

        for media in medias:
            if followed >= session_limit:
                log(f"⚠️ Session follow limit {session_limit}", "WARNING")
                break
            if not self.state.can_follow():
                break

            try:
                user_id  = getattr(media.user, "pk",       None)
                username = getattr(media.user, "username", "unknown")

                # Validate user_id
                uid_ok, uid_err = Validator.validate_user_id(user_id)
                if not uid_ok:
                    log(f"⚠️ {uid_err}", "WARNING")
                    continue

                # Blacklist
                if self.dupes.is_blacklisted(user_id, username):
                    log(f"🚫 Blacklisted @{username}", "INFO")
                    self.session_stats["skipped"] += 1
                    continue

                # Anti-duplication
                if self.dupes.has_followed(user_id):
                    log(f"⏭️ Already followed @{username}", "INFO")
                    self.session_stats["skipped"] += 1
                    continue

                # Follow
                _, success = self.retry.execute(
                    self.client.user_follow,
                    user_id,
                    max_attempts=3,
                    action_name=f"follow @{username}"
                )

                if success:
                    self.dupes.mark_followed(user_id, username)
                    self.state.increment("followed")
                    self.session_stats["followed"] += 1
                    followed += 1
                    log(
                        f"✅ Followed @{username} "
                        f"[{followed}/{session_limit}] "
                        f"[rem:{self.state.get_remaining('followed')}]",
                        "SUCCESS"
                    )
                    random_delay(self.config["delays"]["between_follows"])
                else:
                    self._record_error(f"Follow failed @{username}")

            except BotFatalError:
                raise
            except Exception as e:
                self._record_error(f"Follow loop: {str(e)[:80]}")
                time.sleep(5)

        return followed

    # ─────────────────────────────────────────
    # FOLLOW BY ACCOUNT FOLLOWERS
    # ─────────────────────────────────────────

    def follow_by_account_followers(
        self,
        target_username: str
    ) -> int:
        if not target_username or \
           not isinstance(target_username, str):
            log("❌ Invalid target_username", "ERROR")
            return 0

        if not self.state.can_follow():
            return 0

        log(f"👥 Followers of @{target_username}", "ACTION")
        session_limit = self.config["limits"]["follow_per_session"]
        followed      = 0

        # Get user ID
        user_id, ok = self.retry.execute(
            self.client.user_id_from_username,
            target_username,
            max_attempts=3,
            action_name=f"get id @{target_username}"
        )
        if not ok or user_id is None:
            log(f"❌ Not found: @{target_username}", "ERROR")
            return 0

        # Get followers
        followers, ok = self.retry.execute(
            self.client.user_followers,
            user_id,
            amount=50,
            max_attempts=3,
            action_name=f"followers @{target_username}"
        )
        if not ok or followers is None:
            log(f"❌ Cannot fetch followers @{target_username}", "ERROR")
            return 0

        log(f"📱 {len(followers)} followers", "INFO")

        for uid, user_info in list(followers.items())[:session_limit]:
            if followed >= session_limit:
                break
            if not self.state.can_follow():
                break

            try:
                username = getattr(user_info, "username", "unknown")

                uid_ok, uid_err = Validator.validate_user_id(uid)
                if not uid_ok:
                    continue

                if self.dupes.is_blacklisted(uid, username):
                    self.session_stats["skipped"] += 1
                    continue

                if self.dupes.has_followed(uid):
                    self.session_stats["skipped"] += 1
                    continue

                _, success = self.retry.execute(
                    self.client.user_follow,
                    uid,
                    max_attempts=3,
                    action_name=f"follow @{username}"
                )

                if success:
                    self.dupes.mark_followed(uid, username)
                    self.state.increment("followed")
                    self.session_stats["followed"] += 1
                    followed += 1
                    log(f"✅ Followed @{username}", "SUCCESS")
                    random_delay(self.config["delays"]["between_follows"])
                else:
                    self._record_error(f"Follow failed @{username}")

            except BotFatalError:
                raise
            except Exception as e:
                self._record_error(f"Account follow: {str(e)[:80]}")

        return followed

    # ─────────────────────────────────────────
    # LIKE BY HASHTAG
    # ─────────────────────────────────────────

    def like_by_hashtag(self, hashtag: str) -> int:
        # Validate
        ok, err = Validator.validate_hashtag(hashtag)
        if not ok:
            log(f"❌ Bad hashtag '{hashtag}': {err}", "ERROR")
            return 0

        # Limit check
        if not self.state.can_like():
            return 0

        hashtag = hashtag.lstrip("#").strip()
        log(f"❤️ Like via #{hashtag}", "ACTION")
        self.dupes.mark_hashtag_used(hashtag)

        limit         = self.config["limits"]["hashtag_posts_to_fetch"]
        session_limit = self.config["limits"]["like_per_session"]
        liked         = 0

        medias = self._fetch_medias(hashtag, limit)
        if not medias:
            log(f"⚠️ No posts for #{hashtag}", "WARNING")
            return 0

        log(f"📱 {len(medias)} posts", "INFO")

        for media in medias:
            if liked >= session_limit:
                log(f"⚠️ Session like limit {session_limit}", "WARNING")
                break
            if not self.state.can_like():
                break

            try:
                username = getattr(media.user, "username", "unknown")
                user_id  = getattr(media.user, "pk",       None)
                media_id = getattr(media,      "id",       None)

                # Validate
                mid_ok, mid_err = Validator.validate_media_id(media_id)
                if not mid_ok:
                    log(f"⚠️ {mid_err}", "WARNING")
                    continue

                # Blacklist
                if self.dupes.is_blacklisted(user_id, username):
                    self.session_stats["skipped"] += 1
                    continue

                # Local duplication (fast path)
                if self.dupes.has_liked(media_id):
                    self.session_stats["skipped"] += 1
                    continue

                # Instagram-side already liked
                if getattr(media, "has_liked", False):
                    self.dupes.mark_liked(media_id, username, hashtag)
                    self.session_stats["skipped"] += 1
                    continue

                # Like
                _, success = self.retry.execute(
                    self.client.media_like,
                    media_id,
                    max_attempts=3,
                    action_name=f"like @{username}"
                )

                if success:
                    self.dupes.mark_liked(media_id, username, hashtag)
                    self.state.increment("liked")
                    self.session_stats["liked"] += 1
                    liked += 1
                    log(
                        f"❤️ Liked @{username} "
                        f"[{liked}/{session_limit}] "
                        f"[rem:{self.state.get_remaining('liked')}]",
                        "SUCCESS"
                    )
                    random_delay(self.config["delays"]["between_likes"])
                else:
                    self._record_error(f"Like failed @{username}")

            except BotFatalError:
                raise
            except Exception as e:
                self._record_error(f"Like loop: {str(e)[:80]}")
                time.sleep(5)

        return liked

    # ─────────────────────────────────────────
    # UNFOLLOW NON-FOLLOWERS
    # ─────────────────────────────────────────

    def unfollow_non_followers(self) -> int:
        if not self.state.can_unfollow():
            return 0

        log("➖ Smart unfollow starting...", "ACTION")
        session_limit = self.config["limits"]["unfollow_per_session"]
        days          = self.config.get("unfollow_after_days", 3)
        unfollowed    = 0

        candidates = self.dupes.get_users_to_unfollow(after_days=days)
        if not candidates:
            log("ℹ️ No users ready to unfollow", "INFO")
            return 0

        log(f"📋 {len(candidates)} candidates", "INFO")

        # Get my ID
        try:
            my_id = self.client.user_id
        except Exception as e:
            log(f"❌ Cannot get my user_id: {e}", "ERROR")
            return 0

        # Get my followers
        my_followers, ok = self.retry.execute(
            self.client.user_followers,
            my_id,
            amount=1000,
            max_attempts=3,
            action_name="fetch my followers"
        )
        follower_ids = set()
        if ok and my_followers is not None:
            follower_ids = {str(k) for k in my_followers.keys()}

        for data in candidates[:session_limit]:
            if unfollowed >= session_limit:
                break
            if not self.state.can_unfollow():
                break

            user_id  = data.get("user_id")
            username = data.get("username", "unknown")

            # Validate
            uid_ok, uid_err = Validator.validate_user_id(user_id)
            if not uid_ok:
                log(f"⚠️ {uid_err}", "WARNING")
                continue

            # Blacklist
            if self.dupes.is_blacklisted(user_id, username):
                log(f"🚫 Blacklisted @{username}", "INFO")
                continue

            try:
                # Follows back → keep
                if str(user_id) in follower_ids:
                    log(f"💚 @{username} follows back", "INFO")
                    self.dupes.mark_unfollowed(user_id)
                    continue

                # Unfollow
                _, success = self.retry.execute(
                    self.client.user_unfollow,
                    int(user_id),
                    max_attempts=3,
                    action_name=f"unfollow @{username}"
                )

                if success:
                    self.dupes.mark_unfollowed(user_id)
                    self.state.increment("unfollowed")
                    self.session_stats["unfollowed"] += 1
                    unfollowed += 1
                    log(
                        f"➖ Unfollowed @{username} "
                        f"[{unfollowed}/{session_limit}] "
                        f"[rem:{self.state.get_remaining('unfollowed')}]",
                        "SUCCESS"
                    )
                    random_delay(
                        self.config["delays"]["between_unfollows"]
                    )
                else:
                    self._record_error(f"Unfollow failed @{username}")

            except BotFatalError:
                raise
            except Exception as e:
                self._record_error(f"Unfollow loop: {str(e)[:80]}")

        return unfollowed

    def get_stats(self) -> dict:
        return self.session_stats
