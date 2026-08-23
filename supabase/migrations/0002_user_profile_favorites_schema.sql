-- MP-008: User profile and favorites schema.
-- Source: version1_mealPlanner_technical.md §4. planning_mode default 'suggestion' per
-- functional spec §2 Q5 / technical spec §7 decision log.

create table user_profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  nonveg_days_per_week int,
  nonveg_day_pattern text[],       -- e.g. {wed, sat}
  dietary_restrictions text[] not null default '{}',
  dinner_style text not null default 'rice',        -- 'rice' | 'tiffin'
  planning_mode text not null default 'suggestion', -- 'reserves' | 'suggestion'
  grocery_day text not null,                        -- day of week
  timezone text not null default 'Asia/Kolkata',    -- IANA string; unused by scheduling in v1
  constraint user_profiles_dinner_style_check check (dinner_style in ('rice', 'tiffin')),
  constraint user_profiles_planning_mode_check check (planning_mode in ('reserves', 'suggestion'))
);

create table user_favorite_dishes (
  user_id uuid not null references user_profiles(id) on delete cascade,
  dish_id uuid not null references dishes(id) on delete cascade,
  primary key (user_id, dish_id)   -- exempt from 10-day rule only; still subject to in-week dedup
);
