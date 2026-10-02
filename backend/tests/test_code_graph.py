import unittest

from src.graphrag.code_graph import CodeGraphRetriever, build_code_graph
from src.models import CodeEntity


class CodeGraphTests(unittest.TestCase):
    def test_expands_from_a_seed_symbol_to_a_called_symbol(self):
        graph = build_code_graph([
            CodeEntity(name="endpoint", type="function", file_path="api.py", line_number=10,
                       dependencies=["service"]),
            CodeEntity(name="service", type="function", file_path="service.py", line_number=4),
        ])

        related = CodeGraphRetriever(graph).expand([
            {"metadata": {"file_path": "api.py", "name": "endpoint"}}
        ])

        self.assertTrue(any(item["name"] == "service" for item in related))


if __name__ == "__main__":
    unittest.main()
