import copy
import importlib.util
from pathlib import Path
import unittest
import yaml

spec = importlib.util.spec_from_file_location("sidecar", Path(__file__).with_name("prepare-crdp-sidecar.py"))
sidecar = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sidecar)


class SidecarTests(unittest.TestCase):
    def fixture(self):
        return {"apiVersion": "serving.knative.dev/v1", "kind": "Service",
                "metadata": {"name": "existing", "annotations": {"run.googleapis.com/ingress": "all"}},
                "spec": {"traffic": [{"revisionName": "old", "percent": 100}],
                         "template": {"metadata": {"name": "old", "annotations": {"run.googleapis.com/vpc-access-egress": "all-traffic"}},
                                      "spec": {"serviceAccountName": "runtime@example.test", "timeoutSeconds": 120,
                                               "containers": [{"image": "old-image", "env": [
                                                   {"name": "existing", "value": "keep"},
                                                   {"name": "CRDPIP", "value": "remote"}],
                                                   "resources": {"limits": {"memory": "512Mi"}}}]}}}}

    def prepare(self, service, port=8090):
        return sidecar.prepare(service, "new-java-image", "crdp:1.3.1", "manager.example.test", "token-secret", "2", port)

    def test_preserves_identity_environment_network_and_updates_ports(self):
        result = self.prepare(self.fixture(), 8092)
        loaded = yaml.safe_load(yaml.safe_dump(result))
        revision = loaded["spec"]["template"]
        containers = revision["spec"]["containers"]
        self.assertEqual(revision["spec"]["serviceAccountName"], "runtime@example.test")
        self.assertEqual(revision["metadata"]["annotations"]["run.googleapis.com/vpc-access-egress"], "all-traffic")
        self.assertEqual(containers[0]["image"], "new-java-image")
        self.assertEqual(containers[0]["ports"], [{"containerPort": 8181}])
        self.assertEqual(containers[0]["startupProbe"]["tcpSocket"]["port"], 8181)
        self.assertIn({"name": "existing", "value": "keep"}, containers[0]["env"])
        self.assertIn({"name": "CRDPIP", "value": "localhost"}, containers[0]["env"])
        self.assertIn({"name": "CRDPPORT", "value": "8092"}, containers[0]["env"])
        self.assertNotIn("ports", containers[1])
        self.assertEqual(containers[1]["startupProbe"]["httpGet"],
                         {"path": "/healthz", "port": 8080})
        self.assertNotIn("tcpSocket", containers[1]["startupProbe"])
        self.assertIn({"name": "REGISTRATION_TOKEN", "valueFrom": {"secretKeyRef": {"name": "token-secret", "key": "2"}}}, containers[1]["env"])
        self.assertEqual(loaded["spec"]["traffic"], [{"latestRevision": True, "percent": 100}])
        self.assertNotIn("name", revision["metadata"])

    def test_rejects_repeat_preparation(self):
        with self.assertRaises(ValueError):
            self.prepare(self.prepare(self.fixture()))

    def test_exported_environment_flags_stay_strings(self):
        service = self.fixture()
        service["spec"]["template"]["spec"]["containers"][0]["env"] = yaml.load(
            "- name: showrevealinternalkey\n  value: yes\n"
            "- name: usersetlookup\n  value: no\n"
            "- name: BATCHSIZE\n  value: 1000\n"
            "- name: flag\n  value: true\n", Loader=sidecar.ServiceLoader)
        service["metadata"]["annotations"]["example/flag"] = True
        result = yaml.safe_load(yaml.safe_dump(self.prepare(service)))
        values = {entry["name"]: entry["value"] for entry in
                  result["spec"]["template"]["spec"]["containers"][0]["env"]}
        self.assertEqual(values["showrevealinternalkey"], "yes")
        self.assertEqual(values["usersetlookup"], "no")
        self.assertEqual(values["BATCHSIZE"], "1000")
        self.assertEqual(values["flag"], "true")
        self.assertEqual(result["metadata"]["annotations"]["example/flag"], "true")
        self.assertIs(result["spec"]["traffic"][0]["latestRevision"], True)

    def test_rejects_conflicting_port(self):
        for port in (0, 8080, 8181, 65536):
            with self.assertRaises(ValueError):
                self.prepare(copy.deepcopy(self.fixture()), port)


if __name__ == "__main__":
    unittest.main()
