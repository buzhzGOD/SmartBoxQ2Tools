import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from q2_cleaner.policy import PackageFact, PolicyError, assert_safe_target
from q2_cleaner.storage import verification_token


class PolicyTests(unittest.TestCase):
    def test_user_application_is_allowed(self) -> None:
        assert_safe_target(
            PackageFact(
                name="com.example.game",
                apk_path="/data/app/~~id/com.example.game/base.apk",
                is_home_handler=False,
                is_current_home=False,
                is_active_ime=False,
                enabled=True,
            )
        )

    def test_home_handler_is_blocked(self) -> None:
        with self.assertRaises(PolicyError):
            assert_safe_target(
                PackageFact(
                    name="com.example.home",
                    apk_path="/data/app/~~id/com.example.home/base.apk",
                    is_home_handler=True,
                    is_current_home=True,
                    is_active_ime=False,
                    enabled=True,
                )
            )

    def test_system_application_is_blocked(self) -> None:
        with self.assertRaises(PolicyError):
            assert_safe_target(
                PackageFact(
                    name="com.vendor.adware",
                    apk_path="/system/priv-app/adware/adware.apk",
                    is_home_handler=False,
                    is_current_home=False,
                    is_active_ime=False,
                    enabled=True,
                )
            )

    def test_token_is_stable_and_device_specific(self) -> None:
        token = verification_token("Q2-01", "a" * 64, 2)
        self.assertEqual(token, verification_token("Q2-01", "a" * 64, 2))
        self.assertNotEqual(token, verification_token("Q2-02", "a" * 64, 2))


if __name__ == "__main__":
    unittest.main()
