import copy
import unittest

from ops.tests.fullstack_db_guard import (
    validate_target,
    validate_topology,
)


class FullstackDatabaseGuardTests(unittest.TestCase):
    def setUp(self):
        self.config = {
            "name": "dc-inventory-dev",
            "services": {
                "postgres": {
                    "ports": [{
                        "target": 5432,
                        "published": "55432",
                        "host_ip": "127.0.0.1",
                    }]
                }
            },
        }

        self.container = {
            "State": {"Running": True},
            "Config": {
                "Labels": {
                    "com.docker.compose.project": "dc-inventory-dev",
                    "com.docker.compose.service": "postgres",
                    "com.docker.compose.config-hash": "expected-hash",
                }
            },
            "NetworkSettings": {
                "Ports": {
                    "5432/tcp": [{
                        "HostIp": "127.0.0.1",
                        "HostPort": "55432",
                    }]
                }
            },
        }

    def check(self, config=None, container=None, expected_hash="expected-hash"):
        validate_topology(
            config or self.config,
            container or self.container,
            expected_hash,
            55432,
        )

    def test_matching_topology_passes(self):
        self.check()

    def test_wrong_published_port_fails(self):
        config = copy.deepcopy(self.config)
        config["services"]["postgres"]["ports"][0]["published"] = "55433"

        with self.assertRaises(ValueError):
            self.check(config=config)

    def test_wrong_runtime_port_fails(self):
        container = copy.deepcopy(self.container)
        container["NetworkSettings"]["Ports"]["5432/tcp"][0]["HostPort"] = "55433"

        with self.assertRaises(ValueError):
            self.check(container=container)

    def test_container_configuration_drift_fails(self):
        with self.assertRaises(ValueError):
            self.check(expected_hash="wrong-hash")

    def test_wrong_database_url_port_fails(self):
        with self.assertRaises(ValueError):
            validate_target(
                "postgresql+asyncpg://user:pass@127.0.0.1:55433/"
                "dc_inventory_fullstack_20260919162957_89126",
                "dc_inventory_fullstack_20260919162957_89126",
                55432,
            )

    def test_wrong_database_url_name_fails(self):
        with self.assertRaises(ValueError):
            validate_target(
                "postgresql+asyncpg://user:pass@127.0.0.1:55432/production",
                "dc_inventory_fullstack_20260919162957_89126",
                55432,
            )


if __name__ == "__main__":
    unittest.main()
