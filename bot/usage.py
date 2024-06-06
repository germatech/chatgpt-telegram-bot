import logging
from datetime import datetime, date
from databases.supabase_client import SupabaseClient


class UsageTracker:
    def __init__(self, user_id, user_name):
        """
        Initializes UsageTracker for a user.
        Loads usage data from Supabase.
        :param user_id: Telegram ID of the user
        :param user_name: Telegram username
        """
        try:
            self.supabase = SupabaseClient().client
            logging.info("Supabase client initialized successfully")
        except Exception as e:
            logging.exception(f"Supabase client did not work: Error is {e}")
        self.user_id = user_id
        self.user_name = user_name
        self.current_cost = None
        self.usage_history = None

    @classmethod
    def create(cls, user_id, user_name):
        # Asynchronous constructor
        try:
            tracker = cls(user_id, user_name)
            tracker.load_initial_data()
            logging.info("Supabase client initialized successfully")
            return tracker
        except Exception as e:
            logging.exception(f"Supabase client did not work {e}")

    def load_initial_data(self):
        # Check if user exists in the 'users' table and add them if they don't
        user_data = (
            self.supabase.table("users")
            .select("*")
            .eq("user_id", self.user_id)
            .execute()
        )
        if not user_data.data:
            # Insert new user
            self.supabase.table("users").insert(
                {"user_id": self.user_id, "user_name": self.user_name}
            ).execute()

            self.add_balance(status="active", amount=1, total_payment=1, payment_method="free-plan")

        # Initialize or fetch current cost from 'current_costs' table
        self.current_cost = self.initialize_or_fetch_current_cost()

        # Fetch usage history from 'usage_history' table
        self.usage_history = self.fetch_usage_history()

    def initialize_or_fetch_current_cost(self):
        current_cost_data = (
            self.supabase.table("current_costs")
            .select("*")
            .eq("user_id", self.user_id)
            .execute()
        )
        if not current_cost_data.data:
            # Initialize cost data for a new user
            current_cost = {
                "day": 0.0,
                "month": 0.0,
                "all_time": 0.0,
                "last_update": datetime.now().isoformat(),
            }
            self.supabase.table("current_costs").insert(
                {
                    "user_id": self.user_id,
                    "day": current_cost["day"],
                    "month": current_cost["month"],
                    "all_time": current_cost["all_time"],
                    "last_update": current_cost["last_update"],
                }
            ).execute()
            return current_cost
        else:
            return current_cost_data.data[0]

    def fetch_usage_history(self):
        usage_history_data = (
            self.supabase.table("usage_history")
            .select("*")
            .eq("user_id", self.user_id)
            .execute()
        )
        if usage_history_data.data:
            return usage_history_data.data[0]
        else:
            # Initialize empty usage history for new user
            empty_history = {
                "user_id": self.user_id,
                "date": date.today().isoformat(),
                "chat_tokens": {},
                "transcription_seconds": {},
                "number_images": {},
                "tts_characters": {},
                "vision_tokens": {},
            }
            self.supabase.table("usage_history").insert(empty_history).execute()
            return empty_history

    def add_chat_tokens(self, tokens, tokens_price=0.03):
        """
        Adds used tokens from a request to a user's usage history and updates current cost.
        :param tokens: total tokens used in last request
        :param tokens_price: price per 1000 tokens, defaults to 0.002
        """
        today = date.today().isoformat()
        token_cost = round(float(tokens) * tokens_price / 1000, 6)
        self.add_current_costs(token_cost)

        # Fetch current usage history for the user
        usage_history = (
            self.supabase.table("usage_history")
            .select("*")
            .eq("user_id", self.user_id)
            .execute()
            .data
        )
        if usage_history:
            usage_history = usage_history[0]
            chat_tokens = usage_history.get("chat_tokens", {})
            chat_tokens[today] = chat_tokens.get(today, 0) + tokens
            # update the user balance
            resp = self.balance_consuming(token_cost)
            logging.info(f"users new balance is {resp}")
            # Update the usage_history in the database
            self.supabase.table("usage_history").update(
                {"chat_tokens": chat_tokens}
            ).eq("user_id", self.user_id).execute()
        else:
            # Initialize chat_tokens history
            self.supabase.table("usage_history").insert(
                {"user_id": self.user_id, "chat_tokens": {today: tokens}}
            ).execute()

    def get_current_token_usage(self):
        """
        Get token amounts used for today and this month.
        :return: total number of tokens used per day and per month
        """
        today_str = date.today().isoformat()
        month_str = today_str[:7]  # year-month as string

        usage_history = (
            self.supabase.table("usage_history")
            .select("*")
            .eq("user_id", self.user_id)
            .execute()
            .data
        )
        if usage_history:
            usage_history = usage_history[0]
            chat_tokens = usage_history.get("chat_tokens", {})
            usage_day = chat_tokens.get(today_str, 0)
            usage_month = sum(
                tokens
                for day, tokens in chat_tokens.items()
                if day.startswith(month_str)
            )
        else:
            usage_day, usage_month = 0, 0

        return usage_day, usage_month

    def add_current_costs(self, request_cost):
        """
        Add current cost to all_time, day, and month cost and update last_update date.
        """
        today = date.today()

        # Fetch current costs from the database
        current_cost_data = (
            self.supabase.table("current_costs")
            .select("*")
            .eq("user_id", self.user_id)
            .execute()
            .data
        )
        if current_cost_data:
            current_cost = current_cost_data[0]
            last_update = date.fromisoformat(current_cost["last_update"])

            # Update costs
            current_cost["all_time"] += request_cost
            if today == last_update:
                current_cost["day"] += request_cost
                current_cost["month"] += request_cost
            else:
                current_cost["day"] = request_cost
                if today.month == last_update.month:
                    current_cost["month"] += request_cost
                else:
                    current_cost["month"] = request_cost
            current_cost["last_update"] = today.isoformat()

            # Update the record in the database
            self.supabase.table("current_costs").update(current_cost).eq(
                "user_id", self.user_id
            ).execute()
        else:
            # Initialize a new cost record if it doesn't exist
            new_cost_record = {
                "user_id": self.user_id,
                "day": request_cost,
                "month": request_cost,
                "all_time": request_cost,
                "last_update": today.isoformat(),
            }
            self.supabase.table("current_costs").insert(new_cost_record).execute()

    def add_image_request(self, image_size, image_prices="0.016,0.018,0.08"):
        """
        Add image request to users usage history and update current costs.
        :param image_size: requested image size
        :param image_prices: prices for images of sizes ["256x256", "512x512", "1024x1024"],
                             defaults to [0.016, 0.018, 0.08]
        """
        sizes = ["256x256", "512x512", "1024x1024"]
        requested_size = sizes.index(image_size)
        image_cost = image_prices[requested_size]
        logging.info(f"thw cost is {image_cost}")
        logging.info(f"the type of the cost is {type(image_cost)}")
        today = date.today().isoformat()
        self.add_current_costs(image_cost)

        # Fetch current usage history for the user
        usage_history = (
            self.supabase.table("usage_history")
            .select("*")
            .eq("user_id", self.user_id)
            .execute()
            .data
        )
        if usage_history:
            usage_history = usage_history[0]
            number_images = usage_history.get("number_images", {})
            current_day_images = number_images.get(today, [0, 0, 0])
            current_day_images[requested_size] += 1
            number_images[today] = current_day_images
            self.add_current_costs(image_cost)
            # update the user balance
            resp = self.balance_consuming(image_cost)
            logging.info(f"users new balance is {resp}")

            # Update the usage_history in the database
            self.supabase.table("usage_history").update(
                {"number_images": number_images}
            ).eq("user_id", self.user_id).execute()
        else:
            # Initialize number_images history
            self.supabase.table("usage_history").insert(
                {
                    "user_id": self.user_id,
                    "number_images": {
                        today: [0 if i != requested_size else 1 for i in range(3)]
                    },
                }
            ).execute()

    def get_current_image_count(self):
        """
        Get number of images requested for today and this month.
        :return: total number of images requested per day and per month
        """
        today_str = date.today().isoformat()
        month_str = today_str[:7]  # year-month as string

        usage_history = (
            self.supabase.table("usage_history")
            .select("*")
            .eq("user_id", self.user_id)
            .execute()
            .data
        )
        if usage_history:
            usage_history = usage_history[0]
            number_images = usage_history.get("number_images", {})
            usage_day = sum(number_images.get(today_str, [0, 0, 0]))
            usage_month = sum(
                sum(images)
                for day, images in number_images.items()
                if day.startswith(month_str)
            )
        else:
            usage_day, usage_month = 0, 0

        return usage_day, usage_month

    def add_vision_tokens(self, tokens, vision_token_price=0.03):
        """
        Adds requested vision tokens to a user's usage history and updates current cost.
        :param tokens: total tokens used in last request
        :param vision_token_price: price per 1K tokens transcription, defaults to 0.01
        """
        today = date.today().isoformat()
        token_cost = round(tokens * vision_token_price / 1000, 5)
        logging.info(f"token cost {token_cost}")

        # Fetch and update usage history
        usage_history = (
            self.supabase.table("usage_history")
            .select("*")
            .eq("user_id", self.user_id)
            .execute()
            .data
        )
        if usage_history:
            usage_history = usage_history[0]
            vision_tokens = usage_history.get("vision_tokens", {})
            vision_tokens[today] = vision_tokens.get(today, 0) + tokens
            self.add_current_costs(token_cost)
            # update the user balance
            resp = self.balance_consuming(token_cost)
            logging.info(f"users new balance is {resp}")
            # Update the usage_history in the database
            self.supabase.table("usage_history").update(
                {"vision_tokens": vision_tokens}
            ).eq("user_id", self.user_id).execute()
        else:
            # Initialize vision tokens history
            self.supabase.table("usage_history").insert(
                {"user_id": self.user_id, "vision_tokens": {today: tokens}}
            ).execute()

    def get_current_vision_tokens(self):
        """
        Get vision tokens for today and this month.
        :return: total amount of vision tokens per day and per month
        """
        today_str = date.today().isoformat()
        month_str = today_str[:7]  # year-month as string

        usage_history = (
            self.supabase.table("usage_history")
            .select("*")
            .eq("user_id", self.user_id)
            .execute()
            .data
        )
        if usage_history:
            usage_history = usage_history[0]
            vision_tokens = usage_history.get("vision_tokens", {})
            tokens_day = vision_tokens.get(today_str, 0)
            tokens_month = sum(
                tokens
                for day, tokens in vision_tokens.items()
                if day.startswith(month_str)
            )
        else:
            tokens_day, tokens_month = 0, 0

        return tokens_day, tokens_month

    def add_tts_request(self, text_length, tts_model, tts_prices):
        """
        Add TTS request to user's usage history and update current costs.
        :param text_length: length of text for TTS
        :param tts_model: selected TTS model
        :param tts_prices: dictionary with prices for TTS models
        """
        today = date.today().isoformat()
        price = tts_prices.get(tts_model, 0)
        tts_cost = round(text_length * price / 1000, 2)
        self.add_current_costs(tts_cost)

        # Fetch and update usage history
        usage_history = (
            self.supabase.table("usage_history")
            .select("*")
            .eq("user_id", self.user_id)
            .execute()
            .data
        )
        if usage_history:
            usage_history = usage_history[0]
            tts_characters = usage_history.get("tts_characters", {})
            if tts_model not in tts_characters:
                tts_characters[tts_model] = {}
            tts_characters[tts_model][today] = (
                    tts_characters[tts_model].get(today, 0) + text_length
            )
            self.add_current_costs(tts_cost)
            # update the user balance
            resp = self.balance_consuming(tts_cost)
            logging.info(f"users new balance is {resp}")

            # Update the usage_history in the database
            self.supabase.table("usage_history").update(
                {"tts_characters": tts_characters}
            ).eq("user_id", self.user_id).execute()
        else:
            # Initialize tts_characters history
            self.supabase.table("usage_history").insert(
                {
                    "user_id": self.user_id,
                    "tts_characters": {tts_model: {today: text_length}},
                }
            ).execute()

    def get_current_tts_usage(self):
        """
        Get length of speech generated for today and this month.
        :return: total amount of characters converted to speech per day and per month
        """
        today_str = date.today().isoformat()
        month_str = today_str[:7]  # year-month as string

        usage_history = (
            self.supabase.table("usage_history")
            .select("*")
            .eq("user_id", self.user_id)
            .execute()
            .data
        )
        characters_day = 0
        characters_month = 0
        if usage_history:
            usage_history = usage_history[0]
            tts_characters = usage_history.get("tts_characters", {})
            for tts_model, dates in tts_characters.items():
                characters_day += dates.get(today_str, 0)
                characters_month += sum(
                    characters
                    for day, characters in dates.items()
                    if day.startswith(month_str)
                )
        else:
            characters_day, characters_month = 0, 0

        return int(characters_day), int(characters_month)

    def add_transcription_seconds(self, seconds, minute_price=0.006):
        """
        Adds requested transcription seconds to a user's usage history and updates current cost.
        :param seconds: total seconds used in last request
        :param minute_price: price per minute transcription, defaults to 0.006
        """
        today = date.today().isoformat()
        transcription_cost = round(seconds * minute_price / 60, 2)
        self.add_current_costs(transcription_cost)

        # Fetch and update usage history
        usage_history = (
            self.supabase.table("usage_history")
            .select("*")
            .eq("user_id", self.user_id)
            .execute()
            .data
        )
        if usage_history:
            usage_history = usage_history[0]
            transcription_seconds = usage_history.get("transcription_seconds", {})
            transcription_seconds[today] = transcription_seconds.get(today, 0) + seconds
            self.add_current_costs(transcription_cost)
            # update the user balance
            resp = self.balance_consuming(transcription_cost)
            logging.info(f"users new balance is {resp}")
            # Update the usage_history in the database
            self.supabase.table("usage_history").update(
                {"transcription_seconds": transcription_seconds}
            ).eq("user_id", self.user_id).execute()
        else:
            # Initialize transcription_seconds history
            self.supabase.table("usage_history").insert(
                {"user_id": self.user_id, "transcription_seconds": {today: seconds}}
            ).execute()

    def get_current_transcription_duration(self):
        """
        Get minutes and seconds of audio transcribed for today and this month.
        :return: total amount of time transcribed per day and per month (4 values)
        """
        today_str = date.today().isoformat()
        month_str = today_str[:7]  # year-month as string

        usage_history = (
            self.supabase.table("usage_history")
            .select("*")
            .eq("user_id", self.user_id)
            .execute()
            .data
        )
        seconds_day = 0
        seconds_month = 0
        if usage_history:
            usage_history = usage_history[0]
            transcription_seconds = usage_history.get("transcription_seconds", {})
            seconds_day = transcription_seconds.get(today_str, 0)
            seconds_month = sum(
                seconds
                for day, seconds in transcription_seconds.items()
                if day.startswith(month_str)
            )

        minutes_day, remaining_seconds_day = divmod(seconds_day, 60)
        minutes_month, remaining_seconds_month = divmod(seconds_month, 60)
        return (
            int(minutes_day),
            round(remaining_seconds_day, 2),
            int(minutes_month),
            round(remaining_seconds_month, 2),
        )

    def get_current_cost(self):
        """
        Get total USD amount of all requests of the current day and month
        :return: cost of current day, month, and all time
        """
        today = date.today().isoformat()

        # Fetch current costs from the database
        current_cost_data = (
            self.supabase.table("current_costs")
            .select("*")
            .eq("user_id", self.user_id)
            .execute()
            .data
        )
        if current_cost_data:
            current_cost = current_cost_data[0]
            last_update = date.fromisoformat(current_cost["last_update"])

            cost_day = current_cost["day"] if today == last_update.isoformat() else 0.0
            cost_month = (
                current_cost["month"]
                if today[:7] == last_update.isoformat()[:7]
                else 0.0
            )
            cost_all_time = current_cost["all_time"]
        else:
            cost_day, cost_month, cost_all_time = 0.0, 0.0, 0.0

        return {
            "cost_today": cost_day,
            "cost_month": cost_month,
            "cost_all_time": cost_all_time,
        }

    def initialize_all_time_cost(
            self,
            tokens_price=0.03,
            image_prices="0.016,0.018,0.08",
            minute_price=0.006,
            vision_token_price=0.03,
            tts_prices="0.015,0.030",
    ):
        """
        Calculate total USD amount of all requests in history from the database.
        :param tokens_price: price per 1000 tokens, defaults to 0.002
        :param image_prices: prices for images of sizes ["256x256", "512x512", "1024x1024"],
            defaults to [0.016, 0.018, 0.02]
        :param minute_price: price per minute transcription, defaults to 0.006
        :param vision_token_price: price per 1K vision token interpretation, defaults to 0.01
        :param tts_prices: price per 1K characters tts per model ['tts-1', 'tts-1-hd'], defaults to [0.015, 0.030]
        :return: total cost of all requests
        """
        # Fetch usage history from the database
        usage_history = (
            self.supabase.table("usage_history")
            .select("*")
            .eq("user_id", self.user_id)
            .execute()
            .data
        )
        if not usage_history:
            return 0

        usage_history = usage_history[0]

        # Calculate costs for each type of usage
        total_tokens = sum(usage_history["chat_tokens"].values())
        token_cost = round(total_tokens * tokens_price / 1000, 6)

        total_images = [
            sum(values) for values in zip(*usage_history["number_images"].values())
        ]
        image_prices_list = [float(x) for x in image_prices.split(",")]
        image_cost = sum(
            [count * price for count, price in zip(total_images, image_prices_list)]
        )

        total_transcription_seconds = sum(
            usage_history["transcription_seconds"].values()
        )
        transcription_cost = round(total_transcription_seconds * minute_price / 60, 2)

        total_vision_tokens = sum(usage_history["vision_tokens"].values())
        vision_cost = round(total_vision_tokens * vision_token_price / 1000, 2)

        tts_prices_list = [float(x) for x in tts_prices.split(",")]
        tts_cost = sum(
            [
                sum(tts_model.values()) * price / 1000
                for tts_model, price in zip(
                usage_history["tts_characters"].values(), tts_prices_list
            )
            ]
        )

        # Sum all costs
        all_time_cost = (
                token_cost + image_cost + transcription_cost + vision_cost + tts_cost
        )
        return all_time_cost

    def update_user_model(self, model_name):
        """
        Updates a user's model name setting. If the user has an existing setting, it updates the model name.
        Otherwise, it creates a new setting entry with the specified model name.

        :param model_name: Model name to set for the user.
        """
        # Fetch existing setting
        existing_setting = (
            self.supabase.table("user_settings")
            .select("*")
            .eq("user_id", self.user_id)
            .execute()
        )

        if existing_setting.data:
            # Update existing setting with the new model name
            update_data = {
                "model_name": model_name,
                "last_update": datetime.now().isoformat(),
            }
            self.supabase.table("user_settings").update(update_data).eq(
                "user_id", self.user_id
            ).execute()
        else:
            # Insert new setting with model name
            new_setting = {
                "user_id": self.user_id,
                "model_name": model_name,
                "brain": "assistant",
                "last_update": datetime.now().isoformat(),
            }
            self.supabase.table("user_settings").insert(new_setting).execute()

    def update_user_brain(self, brain):
        """
        Updates a user's brain setting. If the user has an existing setting, it updates the brain setting.
        Otherwise, it creates a new setting entry with the specified brain.

        :param brain: Brain setting to set for the user.
        """
        # Fetch existing setting
        existing_setting = (
            self.supabase.table("user_settings")
            .select("*")
            .eq("user_id", self.user_id)
            .execute()
        )

        if existing_setting.data:
            # Update existing setting with the new brain
            update_data = {"brain": brain, "last_update": datetime.now().isoformat()}
            self.supabase.table("user_settings").update(update_data).eq(
                "user_id", self.user_id
            ).execute()
        else:
            # Insert new setting with brain
            new_setting = {
                "user_id": self.user_id,
                "model_name": "gpt-3.5-turbo-0125",  # Assuming default or empty initial value
                "brain": brain,
                "last_update": datetime.now().isoformat(),
            }
            self.supabase.table("user_settings").insert(new_setting).execute()

    def get_user_setting(self):
        """
        Retrieves the current settings for a user.
        """
        logging.info("user settings are coming")
        setting = (
            self.supabase.table("user_settings")
            .select("*")
            .eq("user_id", self.user_id)
            .execute()
        )

        if setting.data:
            logging.info(f"user settings {setting.data[0]}")
            return setting.data[0]
        else:
            return None

    def add_balance(self, amount: float, payment_method, total_payment, status="active"):
        """
        Adds a balance to the user's account and records the transaction in the 'payments' table.
        :param amount: The amount of money being added.
        :param payment_method: The payment method used for the transaction.
        :param status: The status of the payment, default is 'active'.
        :param total_payment: how much is the budget
        """
        # Insert into payments table
        resp = self.supabase.table("payments").insert(
            {
                "user_id": self.user_id,
                "amount": amount,
                "total_payment": total_payment,
                "payment_method": payment_method,
                "status": status,
            }
        ).execute()
        if resp.data:
            return resp.data[0]
        else:
            return None

    def update_balance(self, amount, total_payment):
        pass

    def get_balance(self, status="active"):
        """
        Retrieves the balance for a specific user based on the specified payment status from the 'payments' table.

        This method queries the 'payments' table in the Supabase database, selecting
        the 'amount' where the 'user_id' matches
        the user ID associated with this instance of the class and the payment
        'status' matches the provided status argument.

        Args:
            status (str, optional): The status of the payments to include in the balance calculation.
                Defaults to 'active', but can be adjusted to match any status
                type stored in the database (e.g., 'completed', 'pending').

        Returns:
            The amount of the first matching payment record if any records are found,
            otherwise None. This method expects that
            the query will return a balance related to a specific status. If no
            records match the query, None is returned.

        Notes:
            - The method logs the fetched balance data if any data is found.
            - Currently, the method retrieves only the first record's amount from potentially multiple records.
              Depending on requirements, modifications might be necessary to sum
              amounts or handle multiple records appropriately.
        """
        balance = (
            self.supabase.table("payments")
            .select("amount")
            .eq("user_id", self.user_id)
            .eq("status", status)
            .execute()
        )
        if balance.data:
            logging.info(f"user balance is: {balance.data[0]}")
            return balance.data[0]
        else:
            return None

    def balance_consuming(self, token_usage_in_dollar):
        balance = self.get_balance()
        logging.info(f"the token usage in dollar {token_usage_in_dollar}")
        remaining_balance = balance["amount"] - token_usage_in_dollar
        if remaining_balance < 0:
            remaining_balance = 0.0
        data = (
            self.supabase.table("payments")
            .update({"amount": remaining_balance})
            .eq("user_id", self.user_id)
            .execute()
        )
        return data.data[0]

    def get_the_total_user_budget(self, status="active"):
        user_budget = (
            self.supabase.table("payments")
            .select("total_payment")
            .eq("user_id", self.user_id)
            .eq("status", status)
            .execute()
        )

        if user_budget.data:
            return user_budget.data[0]
        else:
            return None
