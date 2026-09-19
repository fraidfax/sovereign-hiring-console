import unittest

from app.scoring import score_candidate

JOB = {
    "id": "job-2026-eng-004",
    "title": "Backend Engineer",
    "location": "Dublin, Ireland",
    "description": "Build sovereign backend services.",
    "must_have_skills": ["Python", "SQL", "Docker"],
    "nice_to_have_skills": ["Kubernetes", "Terraform"],
    "min_years_experience": 3,
}


def make_candidate(skills, years_experience):
    return {
        "years_experience": years_experience,
        "skills": skills,
        "education": "BSc Computer Science",
        "work_history": "Worked on backend systems for several years.",
        "cover_letter_excerpt": "Excited to apply for this role.",
    }


class ScoreCandidateTests(unittest.TestCase):
    def test_full_match_scores_close_to_100(self):
        candidate = make_candidate(
            ["Python", "SQL", "Docker", "Kubernetes", "Terraform"],
            years_experience=5,
        )

        result = score_candidate(candidate, JOB)

        self.assertGreaterEqual(result["score"], 95.0)
        self.assertLessEqual(result["score"], 100.0)
        self.assertEqual(sorted(result["matched_must_haves"]), ["Docker", "Python", "SQL"])
        self.assertEqual(result["missing_must_haves"], [])

    def test_no_match_scores_low(self):
        candidate = make_candidate(["Photoshop", "Illustrator"], years_experience=0)

        result = score_candidate(candidate, JOB)

        self.assertLess(result["score"], 20.0)
        self.assertEqual(result["matched_must_haves"], [])
        self.assertEqual(
            sorted(result["missing_must_haves"]), ["Docker", "Python", "SQL"]
        )

    def test_explanation_names_missing_must_have(self):
        candidate = make_candidate(["Python", "SQL"], years_experience=5)

        result = score_candidate(candidate, JOB)

        self.assertIn("Docker", result["missing_must_haves"])
        self.assertIn("Docker", result["explanation"])

    def test_scoring_is_deterministic(self):
        candidate = make_candidate(["Python", "Docker"], years_experience=1)

        first = score_candidate(candidate, JOB)
        second = score_candidate(candidate, JOB)

        self.assertEqual(first, second)

    def test_experience_below_bar_is_scaled_and_named_in_explanation(self):
        candidate = make_candidate(["Python", "SQL", "Docker"], years_experience=0)

        result = score_candidate(candidate, JOB)

        self.assertIn("NOT met", result["explanation"])
        self.assertIn("0 yrs", result["explanation"])

    def test_empty_requirement_lists_do_not_crash(self):
        job = {
            "must_have_skills": [],
            "nice_to_have_skills": [],
            "min_years_experience": 0,
        }
        candidate = make_candidate([], years_experience=0)

        result = score_candidate(candidate, job)

        self.assertEqual(result["score"], 100.0)


if __name__ == "__main__":
    unittest.main()
