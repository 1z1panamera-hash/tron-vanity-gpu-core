from __future__ import annotations

import unittest

from vanity18035.core_adapter import CoreTask
from vanity18035.core_protocol import (
    DecodedHit,
    DecodedProgress,
    MessageType,
    ProtocolError,
    decode_hit,
    decode_progress,
    encode_hit,
    encode_hit_ack,
    encode_progress,
    encode_snapshot,
    message_type,
)


class CoreProtocolTests(unittest.TestCase):
    def test_snapshot_has_a_strict_binary_schema(self) -> None:
        task = CoreTask("item-1", "P1", "TLU*Yqvi2", "lease-1", "shard-1", "2048")
        frame = encode_snapshot(42, [task])
        self.assertEqual(message_type(frame), MessageType.SNAPSHOT)
        self.assertNotIn(b"private_key", frame)

    def test_hit_round_trip_requires_age_ciphertext(self) -> None:
        hit = DecodedHit(
            result_id="result-1",
            event_id="event-1",
            item_id="item-1",
            lease_id="lease-1",
            matched_address="T" + "1" * 28 + "Yqvi2",
            encrypted_private_key=(
                "-----BEGIN AGE ENCRYPTED FILE-----\ntest\n"
                "-----END AGE ENCRYPTED FILE-----\n"
            ),
        )
        self.assertEqual(decode_hit(encode_hit(hit)), hit)
        with self.assertRaises(ProtocolError):
            encode_hit(
                DecodedHit(
                    result_id="result-1",
                    event_id="event-1",
                    item_id="item-1",
                    lease_id="lease-1",
                    matched_address=hit.matched_address,
                    encrypted_private_key="plaintext-private-key",
                )
            )

    def test_progress_round_trip_and_malformed_frames(self) -> None:
        progress = DecodedProgress("item-1", "lease-1", "shard-1", "4096")
        frame = encode_progress(progress)
        self.assertEqual(decode_progress(frame), progress)
        with self.assertRaises(ProtocolError):
            decode_progress(frame[:-1])
        with self.assertRaises(ProtocolError):
            decode_progress(frame + b"\x00")

    def test_snapshot_limits_active_targets(self) -> None:
        tasks = [
            CoreTask(f"item-{index}", "P1", "TLU*Yqvi2", f"lease-{index}", "", "")
            for index in range(17)
        ]
        with self.assertRaises(ProtocolError):
            encode_snapshot(1, tasks)

    def test_hit_ack_contains_only_the_result_identifier(self) -> None:
        frame = encode_hit_ack("result-1")
        self.assertEqual(message_type(frame), MessageType.HIT_ACK)
        self.assertIn(b"result-1", frame)
        self.assertNotIn(b"private", frame)


if __name__ == "__main__":
    unittest.main()
