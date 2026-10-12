//! Romaji study view: fixed font metrics, exact word markers, source-anchored edits.
use egui::{Color32, RichText, Sense, TextFormat, text::LayoutJob};

use crate::app::App;
use crate::model::{Action, Loadable};
use crate::study::conversion::span;
use crate::study::timing::playback_seek;
use crate::theme;

fn report(app: &mut App, result: anyhow::Result<()>) {
    if let Err(error) = result {
        app.study.error = Some(error.to_string());
    }
}

pub fn show(app: &mut App, ui: &mut egui::Ui, fullscreen: bool) {
    let now = app.now_playing();
    let playback = now.as_ref().map_or(0, |now| i64::from(now.position_ms));
    let duration = now.as_ref().map_or(0, |now| i64::from(now.duration_ms));
    if let Some(now) = &now {
        ui.label(RichText::new(format!("{} — {}", now.title, now.subtitle)).strong());
    }
    if now.as_ref().is_some_and(|now| !now.local) {
        ui.horizontal_wrapped(|ui| {
            ui.label("Playback is on another device.");
            if let Some(device) = app.local_device_id.clone()
                && ui.button("Play in this app").clicked()
            {
                app.actions.push(Action::Transfer(device));
            }
        });
    }
    let previous_mode = app.settings.lyric_mode;
    ui.horizontal_wrapped(|ui| {
        use crate::study::LyricMode;
        let selected = match app.settings.lyric_mode {
            LyricMode::Romaji => "Romaji",
            LyricMode::Both => "Hiragana + romaji",
            LyricMode::Hiragana => "Hiragana",
        };
        egui::ComboBox::from_id_salt(("lyric-mode", fullscreen))
            .selected_text(selected)
            .show_ui(ui, |ui| {
                ui.selectable_value(&mut app.settings.lyric_mode, LyricMode::Romaji, "Romaji");
                ui.selectable_value(
                    &mut app.settings.lyric_mode,
                    LyricMode::Both,
                    "Hiragana + romaji",
                );
                ui.selectable_value(
                    &mut app.settings.lyric_mode,
                    LyricMode::Hiragana,
                    "Hiragana",
                );
            });
        if ui.button("Follow").clicked() {
            app.lyrics_following = true;
            app.lyrics_line_shown = None;
        }
        if app.study.busy {
            ui.spinner();
        }
    });
    if previous_mode != app.settings.lyric_mode {
        app.mark_settings_dirty();
        app.lyrics_line_shown = None;
    }
    if let Some(error) = app.study.error.clone() {
        ui.label(RichText::new(error).color(Color32::from_rgb(240, 160, 100)));
        ui.horizontal(|ui| {
            if ui.button("Retry save / conversion").clicked() {
                app.study.persist();
            }
            if ui.button("Dismiss").clicked() {
                app.study.error = None;
            }
        });
    }
    egui::CollapsingHeader::new("Options")
        .id_salt(("study-options", fullscreen, now.is_some()))
        .default_open(now.is_none())
        .show(ui, |ui| {
            ui.horizontal(|ui| {
                ui.add(
                    egui::TextEdit::singleline(&mut app.study.link)
                        .hint_text("Paste a Spotify song link")
                        .desired_width((ui.available_width() - 55.0).max(80.0)),
                );
                if ui.button("Play").clicked() {
                    match track_link(&app.study.link) {
                        Some(uri) => {
                            app.actions.push(Action::PlayStudyTrack(uri));
                            app.lyrics_following = true;
                        }
                        None => {
                            app.study.error =
                                Some("Paste a Spotify track link or track URI.".into())
                        }
                    }
                }
            });
            ui.horizontal_wrapped(|ui| {
                if ui
                    .add_enabled(now.is_some(), egui::Button::new("Import lyrics…"))
                    .clicked()
                    && let Some(path) = rfd::FileDialog::new()
                        .set_title("Import UTF-8 lyrics")
                        .add_filter("Lyrics", &["lrc", "txt"])
                        .pick_file()
                {
                    app.study.import(path);
                }
                ui.checkbox(&mut app.study.show_original, "Original Japanese");
                if ui
                    .add_enabled(now.is_some(), egui::Button::new("Refresh"))
                    .clicked()
                {
                    app.refresh_lyrics();
                }
                if app.study.busy {
                    ui.spinner();
                }
            });
            let alternatives = match &app.lyrics {
                Loadable::Loaded(Some(lyrics)) => lyrics.candidates.clone(),
                _ => Vec::new(),
            };
            if !alternatives.is_empty() {
                egui::CollapsingHeader::new("Choose the matching recording’s lyrics")
                    .default_open(app.study.document.is_none())
                    .show(ui, |ui| {
                        ui.small("Several recordings match. Preview and select the one you hear.");
                        for source in alternatives {
                            egui::CollapsingHeader::new(&source.source.candidate).show(ui, |ui| {
                                for line in source.occurrences.iter().take(5) {
                                    ui.label(&line.raw_line);
                                }
                                if ui.button("Use / preview these lyrics").clicked() {
                                    let result = app.study.offer(source);
                                    report(app, result);
                                }
                            });
                        }
                    });
            }
            if app.study.document.is_some() {
                delay_controls(app, ui);
                candidate(app, ui);
                let document = app.study.document.as_ref().unwrap().clone();
                let snapshot = &document.current().snapshot;
                let converted: Vec<_> = app.study.converted.values().cloned().collect();
                let review = document.needs_review(&converted);
                ui.horizontal(|ui| {
                    ui.label(format!(
                        "{} · {}",
                        snapshot.source.provider,
                        if document.current().pinned {
                            "saved locally"
                        } else {
                            "downloaded"
                        }
                    ));
                    if !review.is_empty()
                        && ui
                            .button(format!("Needs review ({})", review.len()))
                            .clicked()
                    {
                        app.study.review_open = !app.study.review_open;
                    }
                    if app.study.undo.is_some() && ui.button("Undo removal").clicked() {
                        let edit = app.study.undo.as_ref().unwrap().clone();
                        let result = app.study.document.as_mut().unwrap().restore(edit);
                        if result.is_ok() {
                            app.study.undo = None;
                            app.study.persist();
                        }
                        report(app, result);
                    }
                });
                ui.small(&snapshot.source.candidate);
                for warning in &snapshot.source.warnings {
                    ui.small(warning);
                }
                if app.study.review_open {
                    review_panel(app, ui, &review);
                }
            }
        });
    if app.study.document.is_none() {
        if app.study.alignment.is_some() {
            automatic_controls(app, ui);
        }
        match &app.lyrics {
            Loadable::Loading => {
                ui.label("Finding lyrics…");
            }
            Loadable::Failed(_) => {
                ui.label("Lyrics could not be downloaded. Retry or import a UTF-8 LRC file.");
            }
            Loadable::Loaded(Some(lyrics)) if lyrics.instrumental => {
                ui.label("Instrumental · no lyrics.");
            }
            _ if now.is_none() => {
                ui.label("Paste a song link, play it here, and follow its romaji.");
            }
            _ => {
                ui.label("No saved lyrics yet. Import an ordinary or enhanced LRC file if no source is found.");
            }
        }
        return;
    }
    automatic_controls(app, ui);
    let document = app.study.document.as_ref().unwrap().clone();
    let snapshot = &document.current().snapshot;
    let active = app.study.active_line(playback);
    let mut cues = app.study.cues();
    if let Some(end) = duration.checked_sub(document.delay_ms) {
        cues.push(end);
        cues.sort_unstable();
    }
    let follow = app.lyrics_following && app.lyrics_line_shown != Some(active);
    let size = if fullscreen { 34.0 } else { 27.0 };
    let quiet = if fullscreen {
        Color32::from_gray(185)
    } else {
        app.palette.text.gamma_multiply(0.7)
    };
    let scroll = crate::autoscroll::show(
        ui,
        egui::ScrollArea::vertical()
            .id_salt(("study-scroll", &document.track_id, fullscreen))
            .auto_shrink([false, false]),
        egui::Vec2b::new(false, true),
        |ui| {
            ui.add_space(12.0);
            if follow && active.is_none() {
                ui.scroll_to_cursor(Some(egui::Align::Min));
            }
            for occurrence in snapshot.playback_order() {
                let line = &snapshot.occurrences[occurrence];
                let output = app.study.output(occurrence).cloned();
                let timings = app.study.timings(occurrence);
                let is_active = active == Some(occurrence);
                let color = if is_active {
                    if fullscreen {
                        Color32::WHITE
                    } else {
                        app.palette.text
                    }
                } else {
                    quiet
                };
                let timed_count = timings.iter().flatten().count();
                let scripts: &[bool] = match app.settings.lyric_mode {
                    crate::study::LyricMode::Romaji => &[false],
                    crate::study::LyricMode::Both => &[true, false],
                    crate::study::LyricMode::Hiragana => &[true],
                };
                let mut line_rect = None;
                for &hiragana in scripts {
                    let font = theme::regular(size);
                    let mut job = LayoutJob::default();
                    job.wrap.max_width = ui.available_width();

                    if let Some(output) = &output {
                        let text = if hiragana {
                            &output.hiragana
                        } else {
                            &output.romaji
                        };
                        let mut cursor = 0;
                        for (index, word) in output.words.iter().enumerate() {
                            let Some(range) = (if hiragana {
                                word.hiragana_span
                            } else {
                                Some(word.output_span)
                            }) else {
                                continue;
                            };
                            job.append(
                                &text[cursor..range[0]],
                                0.0,
                                TextFormat {
                                    font_id: font.clone(),
                                    color,
                                    ..Default::default()
                                },
                            );
                            let timing = timings.get(index).and_then(Option::as_ref);
                            let lit = timing.is_some_and(|timing| {
                                let last_start = timing
                                    .intervals
                                    .last()
                                    .map_or(0, |interval| interval.start_ms);
                                timing.active(
                                    playback,
                                    document.delay_ms,
                                    cues.get(cues.partition_point(|time| *time <= last_start))
                                        .copied(),
                                )
                            });
                            let selected = app.study.selected == Some((occurrence, index));
                            job.append(
                                span(text, &range).unwrap_or(""),
                                0.0,
                                TextFormat {
                                    font_id: font.clone(),
                                    color: if lit { Color32::BLACK } else { color },
                                    background: if lit {
                                        Color32::from_rgb(250, 218, 90)
                                    } else if selected {
                                        Color32::from_rgb(70, 85, 100)
                                    } else {
                                        Color32::TRANSPARENT
                                    },
                                    underline: if word.mapping_status != "mapped" {
                                        egui::Stroke::new(1.0, Color32::from_rgb(240, 160, 100))
                                    } else {
                                        egui::Stroke::NONE
                                    },
                                    ..Default::default()
                                },
                            );
                            cursor = range[1];
                        }
                        job.append(
                            &text[cursor..],
                            0.0,
                            TextFormat {
                                font_id: font.clone(),
                                color,
                                ..Default::default()
                            },
                        );
                        if text.is_empty() {
                            job.append(
                                if output.romaji.is_empty() {
                                    "♪"
                                } else {
                                    "Hiragana unavailable"
                                },
                                0.0,
                                TextFormat {
                                    font_id: font.clone(),
                                    color,
                                    ..Default::default()
                                },
                            );
                        }
                    } else {
                        job.append(
                            if line.raw_line.is_empty() {
                                "♪"
                            } else {
                                &line.raw_line
                            },
                            0.0,
                            TextFormat {
                                font_id: font,
                                color,
                                ..Default::default()
                            },
                        );
                    }
                    let galley = ui.painter().layout_job(job);
                    let (rect, response) = ui.allocate_exact_size(galley.size(), Sense::click());
                    ui.painter().galley(rect.min, galley.clone(), color);
                    crate::autoscroll::row(ui, &response);
                    if response.clicked()
                        && let Some(output) = &output
                        && let Some(pointer) = response.interact_pointer_pos()
                    {
                        let character = galley.cursor_from_pos(pointer - rect.min).index;
                        let text = if hiragana {
                            &output.hiragana
                        } else {
                            &output.romaji
                        };
                        let byte = text
                            .char_indices()
                            .nth(character.into())
                            .map_or(text.len(), |(offset, _)| offset);
                        if let Some(word) = output.words.iter().position(|word| {
                            (if hiragana {
                                word.hiragana_span
                            } else {
                                Some(word.output_span)
                            })
                            .is_some_and(|range| range[0] <= byte && byte < range[1])
                        }) {
                            let result = app.study.select(occurrence, word);
                            report(app, result);
                        }
                    }
                    if response.double_clicked()
                        && let Some(time) = line
                            .start_ms
                            .and_then(|time| playback_seek(time, document.delay_ms, duration))
                    {
                        app.actions.push(Action::Seek(time as u32));
                        app.lyrics_following = true;
                    }
                    line_rect =
                        Some(line_rect.map_or(rect, |previous: egui::Rect| previous.union(rect)));
                }
                if app.study.show_original {
                    ui.label(&line.raw_line);
                }
                if let Some(output) = &output
                    && !output.words.is_empty()
                {
                    let total = output.words.len();
                    let label = if timed_count == total {
                        "Word timed"
                    } else if timed_count > 0 {
                        "Partial word timing"
                    } else if line.start_ms.is_some() {
                        if snapshot
                            .source
                            .warnings
                            .iter()
                            .any(|warning| warning.starts_with("Automatic word timing:"))
                        {
                            "Line timed · word timing missing"
                        } else {
                            "Line timed · automatic timing available"
                        }
                    } else {
                        "Untimed"
                    };
                    let manual = timings.iter().flatten().any(|timing| timing.manual);
                    let generated = timings.iter().flatten().any(|timing| {
                        timing
                            .fragments
                            .iter()
                            .any(|fragment| fragment.source.starts_with("alignment:"))
                    });
                    ui.small(format!(
                        "{label} · {timed_count}/{total}{}",
                        if manual {
                            " · Your timing"
                        } else if generated {
                            " · Local model"
                        } else {
                            ""
                        }
                    ));
                }
                if is_active && follow {
                    let target = line_rect
                        .unwrap()
                        .translate(egui::vec2(0.0, -ui.clip_rect().height() * 0.2));
                    ui.scroll_to_rect(target, Some(egui::Align::Min));
                }
                ui.add_space(18.0);
            }
            ui.add_space(ui.clip_rect().height() * 0.6);
        },
    );
    if ui.rect_contains_pointer(scroll.inner_rect)
        && ui.input(|input| input.smooth_scroll_delta.y != 0.0)
    {
        app.lyrics_following = false;
    }
    app.lyrics_line_shown = Some(active);
    if now.as_ref().is_some_and(|now| now.playing) {
        ui.ctx()
            .request_repaint_after(std::time::Duration::from_millis(30));
    }
    editor(app, ui);
}

fn automatic_controls(app: &mut App, ui: &mut egui::Ui) {
    use crate::study::alignment::Status;
    if let Some(job) = app.study.alignment.clone() {
        let status = job.status.lock().unwrap_or_else(|p| p.into_inner()).clone();
        if let Status::Running(message) = status {
            ui.horizontal_wrapped(|ui| {
                ui.spinner();
                ui.label(message);
                if ui.button("Cancel timing").clicked() {
                    job.cancel.store(true, std::sync::atomic::Ordering::Release);
                    job.update("Cancelling automatic timing…".into());
                }
            });
        }
    } else {
        ui.horizontal_wrapped(|ui| {
            use crate::study::alignment::Method;
            for (method, label, help) in [
                (Method::Tifa, "Time words · TIFA", "Original TIFA pipeline. About 151 MB on first use; results saved per song."),
                (Method::Experimental, "Time words · Experimental", "TIFA + two vocal separators + independent MMS checks. About 2 GB on first use; several minutes per song. Previous results are kept. Listen to check accuracy."),
            ] {
                if ui.add_enabled(!app.study.busy, egui::Button::new(label)).on_hover_text(help).clicked() {
                    match app.study.alignment_request(method) {
                        Ok(request) => app.backend.send(crate::backend::Command::AlignLyrics(Box::new(request))),
                        Err(error) => app.study.alignment_message = Some(error.to_string()),
                    }
                }
            }
        });
    }
    if let Some(message) = &app.study.alignment_message {
        ui.small(message);
    } else if let Some(warning) = app.study.document.as_ref().and_then(|d| {
        d.current()
            .snapshot
            .source
            .warnings
            .iter()
            .find(|w| w.starts_with("Automatic word timing:"))
    }) {
        ui.small(warning.trim_start_matches("Automatic word timing: "));
    }
}

fn delay_controls(app: &mut App, ui: &mut egui::Ui) {
    let delay = app.study.document.as_ref().unwrap().delay_ms;
    let mut changed = delay;
    ui.horizontal_wrapped(|ui| {
        ui.label(format!("Delay: {delay:+} ms"));
        if ui.button("−250 ms").clicked() {
            changed = delay.saturating_sub(250);
        }
        if ui.button("+250 ms").clicked() {
            changed = delay.saturating_add(250);
        }
        if ui.button("Reset delay").clicked() {
            changed = 0;
        }
    });
    if changed != delay {
        let document = app.study.document.as_mut().unwrap();
        document.delay_ms = changed;
        // Delay does not alter conversion or source anchors.
        app.study.persist();
    }
}

fn candidate(app: &mut App, ui: &mut egui::Ui) {
    let candidate = app
        .study
        .document
        .as_ref()
        .and_then(|document| document.candidate.clone());
    if let Some(candidate) = candidate {
        egui::CollapsingHeader::new("Preview other lyrics").show(ui, |ui| {
            ui.label(format!("{} · {}", candidate.source.provider, candidate.source.candidate));
            ui.small("Switching keeps the previous saved snapshot. Changed text may require reattaching edits.");
            for line in candidate.occurrences.iter().take(6) { ui.label(&line.raw_line); }
            for warning in &candidate.source.warnings { ui.small(warning); }
            if candidate.source.imported { ui.small("LRC header offset is already applied: positive offset moves cues later."); }
            ui.horizontal(|ui| {
                if ui.button("Use these lyrics").clicked() {
                    let result = app.study.document.as_mut().unwrap().use_candidate();
                    if result.is_ok() { app.study.selected = None; app.study.persist(); app.lyrics_line_shown = None; }
                    report(app, result);
                }
                if ui.button("Keep current lyrics").clicked() { app.study.document.as_mut().unwrap().candidate = None; app.study.persist(); }
            });
        });
    }
    let previous: Vec<_> = app
        .study
        .document
        .as_ref()
        .unwrap()
        .bundles
        .iter()
        .enumerate()
        .filter(|(index, _)| *index != app.study.document.as_ref().unwrap().active)
        .map(|(_, bundle)| bundle.snapshot.clone())
        .collect();
    if !previous.is_empty() {
        egui::CollapsingHeader::new("Saved lyric versions").show(ui, |ui| {
            for snapshot in previous {
                if ui
                    .button(format!(
                        "Preview {} · {}",
                        snapshot.source.provider,
                        snapshot
                            .source
                            .warnings
                            .iter()
                            .find(|w| w.starts_with("Automatic word timing:"))
                            .unwrap_or(&snapshot.source.candidate)
                    ))
                    .clicked()
                {
                    let result = app.study.document.as_mut().unwrap().offer(snapshot);
                    report(app, result);
                }
            }
        });
    }
}

fn editor(app: &mut App, ui: &mut egui::Ui) {
    let Some((occurrence, index)) = app.study.selected else {
        return;
    };
    let Some(output) = app.study.output(occurrence).cloned() else {
        return;
    };
    let Some(word) = output.words.get(index) else {
        app.study.selected = None;
        return;
    };
    let document = app.study.document.as_ref().unwrap().clone();
    let raw = &document.current().snapshot.occurrences[occurrence].raw_line;
    let mut open = true;
    egui::Window::new("Selected word").id(egui::Id::new("study-word-editor")).open(&mut open).default_width(420.0).show(ui.ctx(), |ui| {
        ui.label(RichText::new(span(&output.romaji, &word.output_span).unwrap_or("")).size(25.0));
        ui.label(word.expected_text.as_deref().unwrap_or("Original mapping needs correction"));
        ui.checkbox(&mut app.study.editor.mapping, "Fix original-text mapping / group");
        if app.study.editor.mapping {
            ui.label(raw);
            let count = raw.chars().count();
            ui.horizontal(|ui| {
                ui.label("From character");
                ui.add(egui::DragValue::new(&mut app.study.editor.mapping_start).range(0..=count));
                ui.label("to");
                ui.add(egui::DragValue::new(&mut app.study.editor.mapping_end).range(0..=count));
            });
            let selected: String = raw.chars().skip(app.study.editor.mapping_start).take(app.study.editor.mapping_end.saturating_sub(app.study.editor.mapping_start)).collect();
            ui.label(format!("Selected original text: {selected}"));
            ui.small("Select the complete affected group. Overlapping reading edits will be kept for review.");
        }
        ui.label("Reading (spaces highlight together)");
        ui.text_edit_singleline(&mut app.study.editor.reading);
        let repeats = document.current().snapshot.occurrences.iter().filter(|line| line.raw_line == *raw).count();
        ui.label(format!("Preview: [ {} ] · applies to {repeats} identical line(s)", app.study.editor.reading.trim()));
        ui.horizontal(|ui| {
            if ui.button("Save reading / mapping").clicked() { let result = app.study.save_reading(); report(app, result); }
            if ui.button("Reset reading").clicked() { let result = app.study.reset_selected(true); report(app, result); }
        });
        if let Some(reason) = &word.mapping_reason { ui.small(reason); }
        if let Some(error) = &app.study.error { ui.colored_label(Color32::from_rgb(240, 160, 100), error); }
    });
    if !open {
        app.study.selected = None;
    }
}

fn review_panel(app: &mut App, ui: &mut egui::Ui, review: &[crate::study::snapshot::ReviewItem]) {
    for item in review {
        let record = app
            .study
            .document
            .as_ref()
            .unwrap()
            .current()
            .edits
            .iter()
            .find(|edit| edit.id() == item.edit_id)
            .cloned();
        let Some(record) = record else {
            continue;
        };
        ui.group(|ui| {
            ui.label(&record.anchor().raw_line);
            ui.label(format!(
                "{} · occurrence {} · {}",
                record.anchor().expected_text,
                record.anchor().occurrence_id + 1,
                item.reason
            ));
            match &record {
                crate::study::snapshot::Edit::Reading { replacement, .. } => {
                    ui.label(format!("Reading: {replacement}"));
                }
                crate::study::snapshot::Edit::Timing { interval, .. } => {
                    ui.label(format!(
                        "Timing: {} → {:?} ms (retained)",
                        interval.start_ms, interval.end_ms
                    ));
                }
            }
            ui.horizontal(|ui| {
                if ui.button("Attach to selected word…").clicked() {
                    let result = (|| {
                        let (occurrence, word) = app
                            .study
                            .selected
                            .ok_or_else(|| anyhow::anyhow!("Select a current word first."))?;
                        let output = app
                            .study
                            .output(occurrence)
                            .ok_or_else(|| anyhow::anyhow!("Wait for conversion."))?;
                        app.study.preview =
                            Some(app.study.document.as_ref().unwrap().attachment_preview(
                                record.id(),
                                output,
                                word,
                            )?);
                        Ok(())
                    })();
                    report(app, result);
                }
                if ui.button("Discard").clicked() {
                    app.study.undo = app.study.document.as_mut().unwrap().discard(record.id());
                    app.study.persist();
                }
            });
        });
    }
    if let Some(preview) = app.study.preview.clone() {
        ui.group(|ui| {
            ui.label(format!(
                "Attach to {} in {} line occurrence(s)",
                preview.edit.anchor().expected_text,
                preview.affected_occurrences.len()
            ));
            ui.label(&preview.edit.anchor().raw_line);
            ui.small("Timing stays at its saved lyric time; replay and adjust it after attaching.");
            if ui.button("Confirm attachment").clicked() {
                let result = app.study.document.as_mut().unwrap().save_edit(preview.edit);
                if result.is_ok() {
                    app.study.preview = None;
                    app.study.persist();
                }
                report(app, result);
            }
            if ui.button("Cancel attachment").clicked() {
                app.study.preview = None;
            }
        });
    }
}

fn track_link(text: &str) -> Option<String> {
    crate::link::parse(text).filter(|uri| {
        uri.strip_prefix("spotify:track:")
            .is_some_and(crate::study::snapshot::valid_track)
    })
}

#[cfg(test)]
mod tests {
    use super::track_link;
    #[test]
    fn study_accepts_track_links_and_rejects_other_spotify_resources() {
        let track = "1lTfD2M6UpJRWi3YLb8qb5";
        assert_eq!(
            track_link(&format!(
                "https://open.spotify.com/intl-ja/track/{track}?si=example"
            )),
            Some(format!("spotify:track:{track}"))
        );
        assert!(track_link(&format!("spotify:album:{track}")).is_none());
        assert!(track_link("spotify:track:too-short").is_none());
        assert!(track_link(&format!("https://example.org/track/{track}")).is_none());
    }
}
