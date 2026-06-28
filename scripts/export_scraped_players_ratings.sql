SELECT
    s.external_id,
    s.first_name,
    s.last_name,
    s.position,
    t.name AS tournament_name,
    COALESCE(
        NULLIF(TRIM(split_part(t.name, '—', 2)), ''),
        NULLIF(TRIM(split_part(t.name, ' - ', 2)), ''),
        t.name
    ) AS rating_division,
    c.name AS club_name,
    s.games_played,
    s.mvp_count,
    s.goals,
    s.assists,
    s.yellow_cards,
    s.red_cards,
    s.current_rating AS computed_rating,
    s.avg_points_per_game,
    s.division_rank,
    s.division_total,
    s.updated_at
FROM scraped_player_stats s
LEFT JOIN clubs c
    ON c.id = s.club_id
LEFT JOIN tournaments t
    ON t.id = c.tournament_id
ORDER BY
    rating_division NULLS LAST,
    computed_rating DESC NULLS LAST,
    club_name NULLS LAST,
    last_name,
    first_name,
    external_id;
