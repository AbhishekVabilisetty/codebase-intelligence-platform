import unittest

from src.analyzers.code_smell_detector import CodeSmellDetector


class CodeSmellDetectorTests(unittest.TestCase):
    def test_deep_nesting_identifies_owning_function_and_deepest_line(self):
        content = """\
def nested(value):
    if value:
        for item in value:
            if item:
                try:
                    if item > 1:
                        return item
                except TypeError:
                    pass
"""
        smells = CodeSmellDetector().detect_in_file("sample.py", content)
        nesting_smells = [smell for smell in smells if smell.type == "deep_nesting"]

        self.assertEqual(len(nesting_smells), 1)
        self.assertIn("Function 'nested'", nesting_smells[0].description)
        self.assertGreater(nesting_smells[0].line_number, 1)


if __name__ == "__main__":
    unittest.main()
