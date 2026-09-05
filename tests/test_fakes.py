import unittest

from tests.fakes import FakeLLM, FakeRunner


class FakeTests(unittest.TestCase):
    def test_fake_llm_returns_scripted(self):
        llm = FakeLLM(["a", "b"])
        self.assertEqual(llm.complete("x"), "a")
        self.assertEqual(llm.complete("x"), "b")

    def test_fake_runner_returns_stdout(self):
        r = FakeRunner(["hello\n"])
        result = r(["any"], capture_output=True, text=True)
        self.assertEqual(result.stdout, "hello\n")
        self.assertEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
