"""Tests for the University system."""

import pytest
from uuid import uuid4

from waystone.game.systems.university import (
    ArcanumRank,
    MasterReputation,
    UniversityStatus,
    NINE_MASTERS,
    ADMISSION_QUESTIONS,
    RANK_ORDER,
    calculate_tuition,
    can_access_room,
    get_random_questions,
    get_university_status,
    clear_university_cache,
    rank_from_string,
    rank_to_display,
    score_answer,
)


class TestArcanumRank:
    """Tests for ArcanumRank enum and helpers."""

    def test_rank_order(self):
        """Test rank ordering."""
        assert RANK_ORDER.index(ArcanumRank.NONE) < RANK_ORDER.index(ArcanumRank.E_LIR)
        assert RANK_ORDER.index(ArcanumRank.E_LIR) < RANK_ORDER.index(ArcanumRank.RE_LAR)
        assert RANK_ORDER.index(ArcanumRank.RE_LAR) < RANK_ORDER.index(ArcanumRank.EL_THE)

    def test_rank_to_display(self):
        """Test display string conversion."""
        assert rank_to_display(ArcanumRank.NONE) == "Non-Arcanum"
        assert rank_to_display(ArcanumRank.E_LIR) == "E'lir"
        assert rank_to_display(ArcanumRank.RE_LAR) == "Re'lar"
        assert rank_to_display(ArcanumRank.EL_THE) == "El'the"

    def test_rank_from_string(self):
        """Test string to rank conversion."""
        assert rank_from_string("none") == ArcanumRank.NONE
        assert rank_from_string("e_lir") == ArcanumRank.E_LIR
        assert rank_from_string("e'lir") == ArcanumRank.E_LIR
        assert rank_from_string("re_lar") == ArcanumRank.RE_LAR
        assert rank_from_string("re'lar") == ArcanumRank.RE_LAR
        assert rank_from_string("el_the") == ArcanumRank.EL_THE
        assert rank_from_string("el'the") == ArcanumRank.EL_THE
        assert rank_from_string("invalid") == ArcanumRank.NONE


class TestMasterReputation:
    """Tests for MasterReputation tracking."""

    def test_initial_reputation(self):
        """Test initial reputation is zero."""
        rep = MasterReputation(master_id="master_lorren")
        assert rep.reputation == 0
        assert rep.interactions == 0

    def test_modify_reputation(self):
        """Test modifying reputation."""
        rep = MasterReputation(master_id="master_lorren")
        rep.modify(10)
        assert rep.reputation == 10
        assert rep.interactions == 1

    def test_reputation_clamping_max(self):
        """Test reputation is clamped at 100."""
        rep = MasterReputation(master_id="master_lorren", reputation=95)
        rep.modify(20)
        assert rep.reputation == 100

    def test_reputation_clamping_min(self):
        """Test reputation is clamped at -100."""
        rep = MasterReputation(master_id="master_hemme", reputation=-95)
        rep.modify(-20)
        assert rep.reputation == -100


class TestUniversityStatus:
    """Tests for UniversityStatus dataclass."""

    def test_initial_status(self):
        """Test initial university status."""
        char_id = uuid4()
        status = UniversityStatus(character_id=char_id)
        assert status.arcanum_rank == ArcanumRank.NONE
        assert status.current_term == 0
        assert status.tuition_paid is False

    def test_get_reputation(self):
        """Test getting reputation for a master."""
        char_id = uuid4()
        status = UniversityStatus(character_id=char_id)
        rep = status.get_reputation("master_lorren")
        assert rep == 0
        assert "master_lorren" in status.master_reputations

    def test_modify_reputation(self):
        """Test modifying reputation through status."""
        char_id = uuid4()
        status = UniversityStatus(character_id=char_id)
        new_rep = status.modify_reputation("master_kilvin", 15)
        assert new_rep == 15
        assert status.get_reputation("master_kilvin") == 15

    def test_total_reputation(self):
        """Test total reputation calculation."""
        char_id = uuid4()
        status = UniversityStatus(character_id=char_id)
        status.modify_reputation("master_lorren", 10)
        status.modify_reputation("master_kilvin", 20)
        status.modify_reputation("master_hemme", -5)
        assert status.total_reputation() == 25

    def test_average_reputation(self):
        """Test average reputation calculation."""
        char_id = uuid4()
        status = UniversityStatus(character_id=char_id)
        status.modify_reputation("master_lorren", 30)
        status.modify_reputation("master_kilvin", 60)
        assert status.average_reputation() == 45.0


class TestNineMasters:
    """Tests for Nine Masters configuration."""

    def test_all_masters_defined(self):
        """Test all nine masters are defined."""
        assert len(NINE_MASTERS) == 9

    def test_master_fields(self):
        """Test each master has required fields."""
        for master_id, master in NINE_MASTERS.items():
            assert "name" in master
            assert "title" in master
            assert "domain" in master

    def test_known_masters(self):
        """Test specific masters are defined correctly."""
        assert NINE_MASTERS["master_lorren"]["name"] == "Lorren"
        assert NINE_MASTERS["master_kilvin"]["domain"] == "Artificery"
        assert NINE_MASTERS["elodin"]["title"] == "Namer"


class TestAdmissionQuestions:
    """Tests for admission examination questions."""

    def test_questions_exist(self):
        """Test admission questions are defined."""
        assert len(ADMISSION_QUESTIONS) > 0
        for category, questions in ADMISSION_QUESTIONS.items():
            assert len(questions) > 0

    def test_question_structure(self):
        """Test each question has required fields."""
        for category, questions in ADMISSION_QUESTIONS.items():
            for q in questions:
                assert "question" in q
                assert "excellent" in q
                assert "good" in q

    def test_get_random_questions(self):
        """Test getting random questions."""
        questions = get_random_questions(5)
        assert len(questions) == 5
        for q in questions:
            assert "category" in q

    def test_get_random_questions_limited(self):
        """Test getting fewer questions than requested."""
        questions = get_random_questions(3)
        assert len(questions) == 3


class TestScoreAnswer:
    """Tests for answer scoring."""

    def test_excellent_answer(self):
        """Test excellent answer scoring."""
        question = {
            "question": "What is the Alar?",
            "excellent": ["belief", "mental discipline"],
            "good": ["focus", "concentration"],
        }
        rating, score = score_answer(question, "The Alar is the belief that shapes reality")
        assert rating == "excellent"
        assert score == 100

    def test_good_answer(self):
        """Test good answer scoring."""
        question = {
            "question": "What is the Alar?",
            "excellent": ["belief", "mental discipline"],
            "good": ["focus", "concentration"],
        }
        rating, score = score_answer(question, "It requires deep concentration")
        assert rating == "good"
        assert score == 70

    def test_adequate_answer(self):
        """Test adequate answer scoring."""
        question = {
            "question": "What is the Alar?",
            "excellent": ["belief"],
            "good": ["focus"],
        }
        rating, score = score_answer(question, "I'm not entirely sure but I think it has something to do with magic")
        assert rating == "adequate"
        assert score == 40

    def test_poor_answer(self):
        """Test poor answer scoring."""
        question = {
            "question": "What is the Alar?",
            "excellent": ["belief"],
            "good": ["focus"],
        }
        rating, score = score_answer(question, "Dunno")
        assert rating == "poor"
        assert score == 10


class TestTuitionCalculation:
    """Tests for tuition calculation."""

    def test_base_tuition_by_rank(self):
        """Test base tuition varies by rank."""
        # E'lir with neutral scores
        t_elir = calculate_tuition(ArcanumRank.E_LIR, 50, {}, 50)
        # Re'lar with neutral scores
        t_relar = calculate_tuition(ArcanumRank.RE_LAR, 50, {}, 50)
        # El'the with neutral scores
        t_elthe = calculate_tuition(ArcanumRank.EL_THE, 50, {}, 50)

        assert t_elir < t_relar < t_elthe

    def test_high_admission_score_reduces_tuition(self):
        """Test high admission score reduces tuition."""
        # Perfect score
        t_high = calculate_tuition(ArcanumRank.E_LIR, 100, {}, 50)
        # Average score
        t_avg = calculate_tuition(ArcanumRank.E_LIR, 50, {}, 50)
        # Low score
        t_low = calculate_tuition(ArcanumRank.E_LIR, 0, {}, 50)

        assert t_high < t_avg < t_low

    def test_positive_reputation_reduces_tuition(self):
        """Test positive master reputation reduces tuition."""
        good_rep = {"master_lorren": MasterReputation("master_lorren", 50)}
        bad_rep = {"master_hemme": MasterReputation("master_hemme", -50)}

        t_good = calculate_tuition(ArcanumRank.E_LIR, 50, good_rep, 50)
        t_bad = calculate_tuition(ArcanumRank.E_LIR, 50, bad_rep, 50)

        assert t_good < t_bad

    def test_tuition_minimum_zero(self):
        """Test tuition cannot be negative."""
        # Even with perfect scores, tuition is at least 0
        perfect_rep = {m: MasterReputation(m, 100) for m in NINE_MASTERS}
        tuition = calculate_tuition(ArcanumRank.E_LIR, 100, perfect_rep, 100)
        assert tuition >= 0


class TestRoomAccess:
    """Tests for room access restrictions."""

    def test_no_requirement_always_accessible(self):
        """Test rooms without requirements are accessible."""
        assert can_access_room(ArcanumRank.NONE, None) is True
        assert can_access_room(ArcanumRank.E_LIR, None) is True

    def test_elir_requirement(self):
        """Test E'lir requirement."""
        assert can_access_room(ArcanumRank.NONE, "e_lir") is False
        assert can_access_room(ArcanumRank.E_LIR, "e_lir") is True
        assert can_access_room(ArcanumRank.RE_LAR, "e_lir") is True

    def test_relar_requirement(self):
        """Test Re'lar requirement."""
        assert can_access_room(ArcanumRank.NONE, "re_lar") is False
        assert can_access_room(ArcanumRank.E_LIR, "re_lar") is False
        assert can_access_room(ArcanumRank.RE_LAR, "re_lar") is True
        assert can_access_room(ArcanumRank.EL_THE, "re_lar") is True


class TestUniversityStatusCache:
    """Tests for university status caching."""

    def test_get_creates_status(self):
        """Test get_university_status creates new status."""
        clear_university_cache()
        char_id = uuid4()
        status = get_university_status(char_id)
        assert status.character_id == char_id
        assert status.arcanum_rank == ArcanumRank.NONE

    def test_get_returns_same_status(self):
        """Test get_university_status returns cached status."""
        clear_university_cache()
        char_id = uuid4()
        status1 = get_university_status(char_id)
        status1.arcanum_rank = ArcanumRank.E_LIR

        status2 = get_university_status(char_id)
        assert status2.arcanum_rank == ArcanumRank.E_LIR

    def test_clear_cache(self):
        """Test clearing the cache."""
        clear_university_cache()
        char_id = uuid4()
        status = get_university_status(char_id)
        status.arcanum_rank = ArcanumRank.RE_LAR

        clear_university_cache()

        new_status = get_university_status(char_id)
        assert new_status.arcanum_rank == ArcanumRank.NONE
