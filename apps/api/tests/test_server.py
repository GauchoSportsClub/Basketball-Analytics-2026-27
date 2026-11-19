import unittest
from unittest.mock import patch

from apps.api.server import (
    _apply_player_column_config,
    _build_pbp_display_rows,
    _extract_team_stat_rows,
    _fetch_espn_site_season_stats,
    _parse_espn_schedule_games,
    apply_pbp_filters,
    canonicalize_insights_payload,
    build_live_stats_from_pbp,
    dataset_filename,
    fetch_recent_season_games,
    normalize_dataset_name,
    normalize_team_id,
    parse_pbp_filters,
    parse_player_table_rows,
    parse_team_table_rows,
    PbpFilterValidationError,
    PbpFilters,
    season_year_from_label,
    validate_insights_payload,
)


class TeamIdTests(unittest.TestCase):
    def test_normalize_team_id(self) -> None:
        self.assertEqual(normalize_team_id("UCSB"), "ucsb")
        self.assertEqual(normalize_team_id("uc-irvine"), "uc-irvine")
        self.assertEqual(normalize_team_id("2540"), "2540")
        with self.assertRaises(ValueError):
            normalize_team_id("***")


class SeasonYearTests(unittest.TestCase):
    def test_season_year_from_label(self) -> None:
        self.assertEqual(season_year_from_label("2025-26"), 2026)
        self.assertEqual(season_year_from_label("2025-2026"), 2026)
        self.assertEqual(season_year_from_label("2026-27"), 2027)
        self.assertEqual(season_year_from_label("2026-2027"), 2027)
        self.assertEqual(season_year_from_label(), 2027)


class EspnTeamStatsParsingTests(unittest.TestCase):
    def test_extract_team_stat_rows(self) -> None:
        payloads = [
            {
                "displayName": "Overall",
                "statistics": [
                    {"name": "wins", "displayName": "Wins", "value": 21, "displayValue": "21"},
                    {"name": "losses", "displayName": "Losses", "value": 9, "displayValue": "9"},
                ],
            }
        ]
        rows = _extract_team_stat_rows("2540", payloads)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["team_id"], "2540")
        self.assertIn("row_key", rows[0])
        self.assertEqual(rows[0]["split"], "Overall")


class DatasetAliasTests(unittest.TestCase):
    def test_dataset_aliases(self) -> None:
        self.assertEqual(normalize_dataset_name("team"), "team")
        self.assertEqual(normalize_dataset_name("player"), "players")
        self.assertEqual(normalize_dataset_name("players"), "players")
        self.assertEqual(normalize_dataset_name("pbp"), "pbp")
        self.assertEqual(dataset_filename("player"), "player.csv")
        self.assertTrue(dataset_filename("pbp").startswith("pbp-"))
        with self.assertRaises(ValueError):
            normalize_dataset_name("games")


class PdfTableParsingTests(unittest.TestCase):
    def test_parse_team_table_rows(self) -> None:
        table = [
            ["SCORING", "2217", "2062"],
            ["Points Per Game", "79.2", "73.6"],
            ["Score by Periods", "1st", "2nd", "OT", "Total"],
            ["UC Santa Barbara", "1053", "1128", "36", "2217"],
            ["Opponents", "914", "1110", "38", "2062"],
        ]
        rows = parse_team_table_rows(table)
        self.assertGreaterEqual(len(rows), 4)
        self.assertEqual(rows[0]["metric"], "SCORING")
        self.assertEqual(rows[0]["team"], "2217")
        self.assertEqual(rows[0]["opp"], "2062")

    def test_parse_player_table_rows(self) -> None:
        table = [
            [
                "#",
                "Player",
                "GP-GS",
                "MIN",
                "AVG/MIN",
                "FG-FGA",
                "FG%",
                "PTS",
                "AVG/P",
            ],
            ["20", "Mahaney, Aidan", "28-28", "922", "32.9", "150-340", ".441", "426", "15.2"],
            ["", "TEAM TOTALS", "", "", "", "", "", "", ""],
        ]
        rows = parse_player_table_rows(table)
        self.assertEqual(len(rows), 2)  # Mahaney + computed Team row
        self.assertEqual(rows[0]["player"], "Mahaney, Aidan")
        self.assertEqual(rows[0]["gp_gs"], "28-28")
        self.assertEqual(rows[1]["player"], "Team")
        self.assertEqual(rows[1]["gp_gs"], "28-28")
        self.assertEqual(rows[1]["pts"], "426")
        self.assertEqual(rows[1]["avg_pts"], "15.2")


class InsightValidationTests(unittest.TestCase):
    def test_validate_insights_payload(self) -> None:
        datasets = [
            {
                "team_id": "ucsb",
                "dataset": "team",
                "columns": ["row_key", "metric", "team", "opp"],
                "rows_by_key": {
                    "scoring": {
                        "row_key": "scoring",
                        "metric": "SCORING",
                        "team": "2217",
                        "opp": "2062",
                    }
                },
            },
            {
                "team_id": "ucsb",
                "dataset": "players",
                "columns": ["row_key", "player", "pts"],
                "rows_by_key": {
                    "mahaney_aidan_20": {
                        "row_key": "mahaney_aidan_20",
                        "player": "Mahaney, Aidan",
                        "pts": "426",
                    }
                },
            },
            {
                "team_id": "pbp",
                "dataset": "pbp",
                "columns": ["id", "clock", "text", "row_key"],
                "rows_by_key": {
                    "play_123": {
                        "id": "123",
                        "clock": "19:59",
                        "text": "Jump ball won by UCSB",
                        "row_key": "play_123",
                    }
                },
            },
        ]

        payload = {
            "insights": [
                {
                    "insight": "UCSB scored more than opponents.",
                    "evidence": [
                        {
                            "team_id": "ucsb",
                            "dataset": "team",
                            "row_key": "scoring",
                            "fields": ["team", "opp"],
                        },
                        {
                            "team_id": "pbp",
                            "dataset": "pbp",
                            "row_key": "play_123",
                            "fields": ["clock", "text"],
                        },
                        {
                            "team_id": "ucsb",
                            "dataset": "players",
                            "row_key": "mahaney_aidan_20",
                            "fields": ["player", "pts"],
                        },
                    ],
                }
            ]
        }

        ok, errors = validate_insights_payload(payload, datasets)
        self.assertTrue(ok)
        self.assertEqual(errors, [])

    def test_validate_insights_payload_rejects_unknown_and_extra_fields(self) -> None:
        datasets = [
            {
                "team_id": "pbp",
                "dataset": "pbp",
                "columns": ["row_key", "clock", "text"],
                "rows_by_key": {"play_1": {"row_key": "play_1", "clock": "19:59", "text": "tip"}},
            }
        ]
        payload = {
            "insights": [
                {
                    "insight": "Test",
                    "evidence": [
                        {
                            "team_id": "2540",
                            "dataset": "pbp",
                            "row_key": "play_1",
                            "fields": ["clock"],
                            "extra": "not allowed",
                        }
                    ],
                    "extra_item": True,
                }
            ],
            "extra_top": "bad",
        }
        ok, errors = validate_insights_payload(payload, datasets)
        self.assertFalse(ok)
        self.assertTrue(any("unknown top-level keys" in err for err in errors))
        self.assertTrue(any("contains unknown keys" in err for err in errors))
        self.assertTrue(any("references unknown dataset (2540/pbp)" in err for err in errors))


class InsightReliabilityTests(unittest.TestCase):
    def _dataset_contexts(self):
        return [
            {
                "team_id": "pbp",
                "dataset": "pbp",
                "columns": ["row_key", "clock", "text"],
                "rows": [{"row_key": "play_1", "clock": "19:59", "text": "Jump ball won by UCSB"}],
                "rows_by_key": {"play_1": {"row_key": "play_1", "clock": "19:59", "text": "Jump ball won by UCSB"}},
            },
            {
                "team_id": "ucsb",
                "dataset": "team",
                "columns": ["row_key", "team", "opp"],
                "rows": [{"row_key": "scoring", "team": "2217", "opp": "2062"}],
                "rows_by_key": {"scoring": {"row_key": "scoring", "team": "2217", "opp": "2062"}},
            },
        ]

    def test_canonicalize_maps_single_pbp_context(self) -> None:
        payload = {
            "insights": [
                {
                    "insight": "PBP trend",
                    "evidence": [
                        {
                            "team_id": "2540",
                            "dataset": "pbp",
                            "row_key": "play_1",
                            "fields": ["clock", "text"],
                        }
                    ],
                }
            ]
        }
        normalized = canonicalize_insights_payload(payload, self._dataset_contexts())
        ref = normalized["insights"][0]["evidence"][0]
        self.assertEqual(ref["team_id"], "pbp")
        self.assertEqual(ref["dataset"], "pbp")


class PbpTableFormattingTests(unittest.TestCase):
    def test_pbp_table_drops_internal_columns_and_reorders(self) -> None:
        rows = [
            {
                "row_key": "play_1",
                "id": "100",
                "sequence": 1,
                "period": "1st",
                "clock": "19:59",
                "text": "Made Jumper.",
                "type": "Made Shot",
                "team_id": "2540",
                "scoring_play": True,
                "shooting_play": True,
                "wallclock": "2026-02-26T01:00:00Z",
            }
        ]
        columns = [
            "id",
            "sequence",
            "period",
            "clock",
            "text",
            "type",
            "team_id",
            "scoring_play",
            "shooting_play",
            "wallclock",
            "row_key",
        ]
        out_columns, out_rows = _build_pbp_display_rows(rows, columns, ucsb_team_id="2540")
        self.assertEqual(out_columns[:3], ["team_id", "type", "text"])
        for forbidden in ("id", "sequence", "wallclock"):
            self.assertNotIn(forbidden, out_columns)
            self.assertNotIn(forbidden, out_rows[0])
        self.assertEqual(out_rows[0]["team_id"], "UCSB")
        self.assertEqual(out_rows[0]["row_key"], "play_1")

    def test_pbp_table_team_labels_use_opponent_for_non_ucsb(self) -> None:
        rows = [
            {"row_key": "play_1", "team_id": "300", "type": "Turnover", "text": "Bad pass", "clock": "18:01"},
            {"row_key": "play_2", "team_id": "2540", "type": "Steal", "text": "Stolen by UCSB", "clock": "17:55"},
        ]
        columns = ["row_key", "team_id", "type", "text", "clock"]
        _, out_rows = _build_pbp_display_rows(rows, columns, ucsb_team_id="2540")
        self.assertEqual(out_rows[0]["team_id"], "Opponent")
        self.assertEqual(out_rows[1]["team_id"], "UCSB")


class LiveStatsRegressionTests(unittest.TestCase):
    def test_live_stats_content_unchanged_by_pbp_table_formatting(self) -> None:
        raw_rows = [
            {
                "team_id": "2540",
                "type": "Made Shot",
                "text": "Made Jumper",
                "scoring_play": True,
                "shooting_play": True,
                "score_value": 2,
                "points_attempted": 2,
                "athlete_id": "11",
                "assist_athlete_id": "22",
            },
            {
                "team_id": "300",
                "type": "Turnover",
                "text": "Lost ball turnover",
                "scoring_play": False,
                "shooting_play": False,
                "score_value": 0,
                "points_attempted": 0,
                "athlete_id": "44",
                "assist_athlete_id": "",
            },
        ]
        with patch("apps.api.server.load_pbp_rows", return_value=raw_rows):
            live = build_live_stats_from_pbp(ucsb_team_id="2540", opponent_team_id="300")
        ucsb_rows = live["ucsb_team"]["rows"]
        pts_row = next(row for row in ucsb_rows if row["stat_key"] == "pts")
        ast_row = next(row for row in ucsb_rows if row["stat_key"] == "ast")
        self.assertEqual(pts_row["value"], "2")
        self.assertEqual(ast_row["value"], "1")


class PbpAdvancedFilterTests(unittest.TestCase):
    def test_parse_pbp_filters_back_compat_empty(self) -> None:
        parsed = parse_pbp_filters({})
        self.assertEqual(parsed, PbpFilters())

    def test_parse_pbp_filters_last_n(self) -> None:
        parsed = parse_pbp_filters(
            {
                "team_id": ["UCSB,Opponent"],
                "type": ["Made Shot"],
                "text": ["jumper"],
                "period": ["2,OT"],
                "clock_mode": ["last_n"],
                "clock_last_n_minutes": ["2.5"],
            }
        )
        self.assertEqual(parsed.team_ids, ["UCSB", "Opponent"])
        self.assertEqual(parsed.periods, ["2", "ot"])
        self.assertEqual(parsed.clock_mode, "last_n")
        self.assertEqual(parsed.clock_last_n_minutes, 2.5)

    def test_parse_pbp_filters_invalid_clock(self) -> None:
        with self.assertRaises(PbpFilterValidationError):
            parse_pbp_filters({"clock_mode": ["range"], "clock_from": ["5:80"], "clock_to": ["2:00"]})

    def test_parse_pbp_filters_invalid_range_order(self) -> None:
        with self.assertRaises(PbpFilterValidationError):
            parse_pbp_filters({"clock_mode": ["range"], "clock_from": ["1:00"], "clock_to": ["5:00"]})

    def test_apply_pbp_filters_combined(self) -> None:
        rows = [
            {"team_id": "2540", "type": "Made Shot", "text": "made jumper", "period": "2nd", "clock": "01:45"},
            {"team_id": "300", "type": "Turnover", "text": "bad pass", "period": "2nd", "clock": "01:20"},
            {"team_id": "2540", "type": "Made Shot", "text": "corner three", "period": "1st", "clock": "00:40"},
        ]
        filters = parse_pbp_filters(
            {
                "team_id": ["UCSB"],
                "type": ["Made Shot"],
                "text": ["jumper"],
                "period": ["2"],
                "clock_mode": ["last_n"],
                "clock_last_n_minutes": ["2"],
            }
        )
        out = apply_pbp_filters(rows, filters, ucsb_team_id="2540")
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["text"], "made jumper")

    def test_apply_pbp_filters_clock_range_inclusive(self) -> None:
        rows = [
            {"team_id": "2540", "type": "Made Shot", "text": "a", "period": "2nd", "clock": "05:00"},
            {"team_id": "2540", "type": "Made Shot", "text": "b", "period": "2nd", "clock": "03:00"},
            {"team_id": "2540", "type": "Made Shot", "text": "c", "period": "2nd", "clock": "02:00"},
            {"team_id": "2540", "type": "Made Shot", "text": "d", "period": "2nd", "clock": "01:59"},
        ]
        filters = parse_pbp_filters(
            {"clock_mode": ["range"], "clock_from": ["05:00"], "clock_to": ["02:00"], "period": ["2"]}
        )
        out = apply_pbp_filters(rows, filters, ucsb_team_id="2540")
        self.assertEqual([row["text"] for row in out], ["a", "b", "c"])

    def test_apply_pbp_filters_last_n_edge_cases(self) -> None:
        rows = [
            {"team_id": "2540", "type": "Made Shot", "text": "0:30 play", "period": "4th", "clock": "00:30"},
            {"team_id": "2540", "type": "Made Shot", "text": "1:00 play", "period": "4th", "clock": "01:00"},
            {"team_id": "2540", "type": "Made Shot", "text": "1:01 play", "period": "4th", "clock": "01:01"},
        ]
        filters = parse_pbp_filters({"clock_mode": ["last_n"], "clock_last_n_minutes": ["1"], "period": ["4"]})
        out = apply_pbp_filters(rows, filters, ucsb_team_id="2540")
        self.assertEqual([row["text"] for row in out], ["0:30 play", "1:00 play"])

    def test_apply_pbp_filters_general_q(self) -> None:
        rows = [
            {"team_id": "2540", "type": "Made Shot", "text": "Corner three", "period": "2nd", "clock": "01:15"},
            {"team_id": "300", "type": "Turnover", "text": "Bad pass", "period": "2nd", "clock": "01:05"},
        ]
        filters = parse_pbp_filters({"q": ["turnover"]})
        out = apply_pbp_filters(rows, filters, ucsb_team_id="2540")
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["type"], "Turnover")


class Season202627ScheduleAndStatsTests(unittest.TestCase):
    def test_parse_espn_schedule_games_labels(self) -> None:
        payload = {
            "events": [
                {
                    "id": "401928353",
                    "date": "2026-11-15T21:00Z",
                    "competitions": [
                        {
                            "neutralSite": False,
                            "status": {"type": {"state": "post", "completed": True}},
                            "competitors": [
                                {"homeAway": "home", "team": {"id": "2540", "location": "UC Santa Barbara"}, "score": {"displayValue": "97"}},
                                {"homeAway": "away", "team": {"id": "3185", "location": "UC Merced"}, "score": {"displayValue": "47"}},
                            ],
                        }
                    ],
                },
                {
                    "id": "401928354",
                    "date": "2026-11-20T02:00Z",
                    "competitions": [
                        {
                            "neutralSite": False,
                            "status": {"type": {"state": "pre", "completed": False}},
                            "competitors": [
                                {"homeAway": "home", "team": {"id": "2492", "location": "Pepperdine"}, "score": {}},
                                {"homeAway": "away", "team": {"id": "2540", "location": "UC Santa Barbara"}, "score": {}},
                            ],
                        }
                    ],
                },
            ]
        }
        games = _parse_espn_schedule_games(payload, team_id="2540")
        self.assertEqual(len(games), 2)
        self.assertEqual(games[0]["label"], "Nov 15 — UCSB vs UC Merced (W 97-47)")
        self.assertEqual(games[0]["opponent_team_id"], "3185")
        self.assertEqual(games[0]["opponent_name"], "UC Merced")
        self.assertEqual(games[1]["label"], "Nov 19 — UCSB @ Pepperdine (Upcoming)")

    def test_fetch_recent_season_games_returns_last_10_newest_first(self) -> None:
        events = []
        for day in range(1, 13):
            events.append(
                {
                    "id": f"4019000{day:02d}",
                    "date": f"2026-11-{day:02d}T21:00Z",
                    "competitions": [
                        {
                            "neutralSite": False,
                            "status": {"type": {"state": "post", "completed": True}},
                            "competitors": [
                                {"homeAway": "home", "team": {"id": "2540", "location": "UC Santa Barbara"}, "score": {"displayValue": "80"}},
                                {"homeAway": "away", "team": {"id": str(100 + day), "location": f"Team {day}"}, "score": {"displayValue": "70"}},
                            ],
                        }
                    ],
                }
            )
        events.append(
            {
                "id": "401999999",
                "date": "2026-12-01T21:00Z",
                "competitions": [
                    {
                        "neutralSite": False,
                        "status": {"type": {"state": "pre", "completed": False}},
                        "competitors": [
                            {"homeAway": "home", "team": {"id": "2540", "location": "UC Santa Barbara"}, "score": {}},
                            {"homeAway": "away", "team": {"id": "13", "location": "Cal Poly"}, "score": {}},
                        ],
                    }
                ],
            }
        )
        with patch("apps.api.server.fetch_json", return_value={"events": events}), patch("apps.api.server.write_json_file"):
            recent = fetch_recent_season_games("2540", limit=10, force_refresh=True)
        self.assertEqual(len(recent), 10)
        self.assertEqual(recent[0]["id"], "401900012")
        self.assertEqual(recent[-1]["id"], "401900003")
        self.assertNotIn("401999999", [g["id"] for g in recent])

    def test_fetch_espn_site_season_stats_maps_to_player_table_config(self) -> None:
        mock_payload = {
            "team": {"id": "2540", "displayName": "UC Santa Barbara Gauchos", "recordSummary": "4-0"},
            "teamTotals": [],
            "results": [
                {
                    "leaders": [
                        {
                            "athlete": {"id": "5105860", "displayName": "Antonio Chol"},
                            "statistics": [
                                {
                                    "name": "general",
                                    "stats": [
                                        {"name": "gamesPlayed", "value": 4, "displayValue": "4"},
                                        {"name": "gamesStarted", "value": 0, "displayValue": "0"},
                                        {"name": "minutes", "value": 53, "displayValue": "53"},
                                        {"name": "rebounds", "value": 9, "displayValue": "9"},
                                        {"name": "avgFouls", "value": 0.5, "displayValue": "0.5"},
                                    ],
                                },
                                {
                                    "name": "offensive",
                                    "stats": [
                                        {"name": "points", "value": 42, "displayValue": "42"},
                                        {"name": "avgPoints", "value": 10.5, "displayValue": "10.5"},
                                        {"name": "assists", "value": 2, "displayValue": "2"},
                                        {"name": "turnovers", "value": 3, "displayValue": "3"},
                                        {"name": "fieldGoalPct", "value": 72.2, "displayValue": "72.2"},
                                        {"name": "freeThrowPct", "value": 63.6, "displayValue": "63.6"},
                                        {"name": "threePointFieldGoalPct", "value": 75.0, "displayValue": "75.0"},
                                    ],
                                },
                                {
                                    "name": "defensive",
                                    "stats": [
                                        {"name": "steals", "value": 1, "displayValue": "1"},
                                        {"name": "blocks", "value": 2, "displayValue": "2"},
                                    ],
                                },
                            ],
                        }
                    ]
                }
            ],
        }
        with patch("apps.api.server.fetch_json", return_value=mock_payload):
            result = _fetch_espn_site_season_stats("2540", 2027)
        self.assertIsNotNone(result)
        school_name, team_rows, player_rows, _ = result
        self.assertEqual(school_name, "UC Santa Barbara Gauchos")
        self.assertEqual(len(player_rows), 1)
        context = {"dataset": "players", "columns": list(player_rows[0].keys()), "rows": player_rows}
        _apply_player_column_config(context)
        row = context["rows"][0]
        self.assertEqual(row["Player"], "Antonio Chol")
        self.assertEqual(row["GP-GS"], "4-0")
        self.assertEqual(row["PTS"], "42")
        self.assertEqual(row["PPG"], "10.5")
        self.assertEqual(row["REB"], "9")
        self.assertEqual(row["RPG"], "2.2")
        self.assertEqual(row["AST"], "2")
        self.assertEqual(row["APG"], "0.5")
        self.assertEqual(row["PF"], "2")
        self.assertEqual(row["FG%"], "72.2")
        self.assertEqual(row["3P%"], "75.0")


if __name__ == "__main__":
    unittest.main()
