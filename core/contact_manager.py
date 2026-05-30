"""[V9.0] J.A.R.V.I.S. ContactManager

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Converts contacts.json to ChromaDB based relationship graph."""

import json

import logging

import os

import time

from typing import Optional



logger = logging.getLogger("JARVIS.ContactManager")

CONTACT_ID_PREFIX = "contact_profile_"



class ContactManager:

    """[V9.0] ChromaDB based contact profile manager."""



    def __init__(self, memory_manager, contacts_path: str = "contacts.json"):

        self.memory = memory_manager

        self.contacts_path = contacts_path

        self._cache: dict[str, dict] = {}



    def setup_contacts(self) -> None:

        """contacts.json → ChromaDB migration (idempotent)."""

        if not os.path.exists(self.contacts_path):

            return



        existing = self._list_contact_ids()

        existing_names = {eid.replace(CONTACT_ID_PREFIX, "") for eid in existing if eid.startswith(CONTACT_ID_PREFIX)}



        try:

            with open(self.contacts_path, encoding="utf-8") as f:

                contacts: dict = json.load(f)

            

            migrated_count = 0

            for name, phone in contacts.items():

                if name not in existing_names:

                    self._upsert_profile(name, self._default_profile(name, phone))

                    migrated_count += 1

                    

            if migrated_count > 0:

                logger.info(f"[CONTACT] {migrated_count} new contact migrated.")

            else:

                logger.info(f"[CONTACT] All contacts ({len(existing)} record) are already in ChromaDB.")

        except Exception as e:

            logger.error(f"[CONTACT] Migration error: {e}")



    def get_profile(self, name: str) -> dict:

        """It pulls the profile from cache or ChromaDB."""

        if name in self._cache:

            return self._cache[name]

        try:

            result = self.memory.collection.get(

                ids=[f"{CONTACT_ID_PREFIX}{name}"],

                include=["documents"]

            )

            if result.get("documents") and result["documents"][0]:

                profile = json.loads(result["documents"][0])

                self._cache[name] = profile

                return profile

        except Exception:

            pass

            

        profile = self._bootstrap_from_json(name)

        if not profile.get("phone"):

            return {"name": name, "phone": "", "unknown": True}

            

        self._upsert_profile(name, profile)

        self._cache[name] = profile

        return profile



    def update_after_message(self, name: str, message_content: str, success: bool) -> None:

        """Updates the profile after successful submission."""

        if not success: return

        profile = self.get_profile(name)

        profile["last_message_at"] = time.time()

        profile["message_count"] = profile.get("message_count", 0) + 1

        topics = profile.get("last_topics", [])

        topics = (topics + [message_content[:80]])[-5:]

        profile["last_topics"] = topics

        self._upsert_profile(name, profile)

        self._cache[name] = profile

        logger.info(f"[CONTACT] Updated profile '{name}'.")



    def _default_profile(self, name: str, phone: str) -> dict:

        return {"name": name, "phone": phone, "tone": "samimi", "message_count": 0, "last_topics": [], "last_message_at": None}



    def _bootstrap_from_json(self, name: str) -> dict:

        try:

            with open(self.contacts_path, encoding="utf-8") as f:

                contacts = json.load(f)

            phone = contacts.get(name, "")

        except: phone = ""

        return self._default_profile(name, phone)



    def _upsert_profile(self, name: str, profile: dict) -> None:

        doc = json.dumps(profile, ensure_ascii=False)

        self.memory.collection.upsert(

            ids=[f"{CONTACT_ID_PREFIX}{name}"],

            documents=[doc],

            metadatas=[{"type": "contact_profile", "name": name}]

        )



    def _list_contact_ids(self) -> list[str]:

        try:

            result = self.memory.collection.get(where={"type": "contact_profile"}, include=[])

            return result.get("ids", [])

        except: return []