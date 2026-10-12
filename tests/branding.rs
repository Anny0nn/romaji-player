use std::path::{Path, PathBuf};
use std::process::Command;

const COMMAND: &str = env!("CARGO_BIN_EXE_spotifast");

struct Scratch(PathBuf);

impl Scratch {
    fn new() -> Self {
        let path =
            std::env::temp_dir().join(format!("spotifast-branding-{:016x}", rand::random::<u64>()));
        std::fs::create_dir(&path).unwrap();
        Self(path)
    }
}

impl Drop for Scratch {
    fn drop(&mut self) {
        let _ = std::fs::remove_dir_all(&self.0);
    }
}

#[test]
fn the_command_reports_its_name_and_passes_the_update_version_check() {
    let output = Command::new(COMMAND).arg("--version").output().unwrap();
    assert!(output.status.success());
    assert_eq!(
        String::from_utf8(output.stdout).unwrap().trim(),
        format!("spotifast {}", env!("CARGO_PKG_VERSION"))
    );
    let help = Command::new(COMMAND).arg("--help").output().unwrap();
    assert!(help.status.success());
    assert!(
        String::from_utf8(help.stdout)
            .unwrap()
            .contains("Usage: spotifast")
    );
    assert_eq!(spotifast::updates::CONFIG.slug, "spotifast");
}

/// The app's name before the rename is gone from everything but the past
/// release notes and the two old guide addresses that still redirect.
/// Spelled in two halves so this file does not match itself.
#[test]
fn no_file_carries_the_old_name() {
    let old = ["fast", "potify"].concat();
    let root = Path::new(env!("CARGO_MANIFEST_DIR"));
    let found = files_carrying_name(root, &old);
    assert!(found.is_empty(), "the old name is still in {found:?}");
}

/// Check publishable source, including new untracked files. Ignored build/model
/// directories and local configuration are not part of the app's branding.
fn files_carrying_name(root: &Path, old: &str) -> Vec<String> {
    let allowed = [
        Path::new("packaging/release-notes"),
        // Old guide URLs still redirect, so links from elsewhere keep working.
        Path::new("docs/_guide/using-spotifast.md"),
        Path::new("docs/_guide/what-is-spotifast.md"),
    ];
    let output = Command::new("git")
        .current_dir(root)
        .args([
            "ls-files",
            "--cached",
            "--others",
            "--exclude-standard",
            "-z",
        ])
        .output()
        .expect("source branding check requires Git");
    assert!(output.status.success(), "Git could not list source files");
    let mut found = Vec::new();
    for name in output
        .stdout
        .split(|byte| *byte == 0)
        .filter(|p| !p.is_empty())
    {
        let relative = String::from_utf8(name.to_vec()).unwrap();
        let path = Path::new(&relative);
        if allowed.iter().any(|allowed| path.starts_with(allowed)) {
            continue;
        }
        let absolute = root.join(path);
        // Never follow a link to content outside this source checkout.
        let text = if absolute.is_file() && !absolute.is_symlink() {
            String::from_utf8_lossy(&std::fs::read(&absolute).unwrap()).to_lowercase()
        } else {
            String::new()
        };
        if relative.to_lowercase().contains(old) || text.contains(old) {
            found.push(relative);
        }
    }
    found.sort();
    found
}

#[test]
fn branding_checks_tracked_and_new_source_without_reading_ignored_local_files() {
    let scratch = Scratch::new();
    let root = &scratch.0;
    assert!(
        Command::new("git")
            .current_dir(root)
            .args(["init", "--quiet"])
            .output()
            .unwrap()
            .status
            .success()
    );
    let old = ["fast", "potify"].concat();
    std::fs::write(root.join(".gitignore"), ".venv/\n.agents\n").unwrap();
    std::fs::create_dir(root.join(".venv")).unwrap();
    std::fs::write(root.join(".venv/third-party.txt"), &old).unwrap();
    std::fs::write(root.join("tracked.txt"), &old).unwrap();
    assert!(
        Command::new("git")
            .current_dir(root)
            .args(["add", "tracked.txt"])
            .output()
            .unwrap()
            .status
            .success()
    );
    std::fs::write(root.join("new.txt"), &old).unwrap();
    #[cfg(unix)]
    std::os::unix::fs::symlink(root.join(".venv"), root.join(".agents")).unwrap();
    assert_eq!(files_carrying_name(root, &old), ["new.txt", "tracked.txt"]);
}

#[test]
fn existing_preferences_and_custom_connect_names_survive_a_save() {
    use spotifast::settings::{Settings, ThemeChoice};

    let scratch = Scratch::new();
    let path = scratch.0.join("settings.json");
    for name in ["Spotifast", "Living room", "Carmine's laptop"] {
        let saved = Settings {
            device_name: name.into(),
            theme: ThemeChoice::Light,
            volume: 37,
            pinned_contexts: vec![
                "spotify:playlist:123".into(),
                spotifast::settings::LIKED_SONGS_KEY.into(),
            ],
            ..Settings::default()
        };
        saved.save(&path);
        assert_eq!(Settings::load(&path), saved);
    }
    assert_eq!(Settings::default().device_name, "Spotifast");
}

#[cfg(target_os = "linux")]
#[test]
fn the_command_forwards_links_to_the_existing_instance_on_a_private_bus() {
    use spotifast::single_instance::{ControlCommand, Outcome};

    const CHILD: &str = "SPOTIFAST_BRANDING_PRIVATE_BUS";
    if std::env::var_os(CHILD).is_none() {
        // A clean build (including Nix) need not have /etc/dbus-1/session.conf.
        // Own the bus configuration too, without loading desktop services.
        let scratch = Scratch::new();
        let config = scratch.0.join("session.conf");
        std::fs::write(
            &config,
            r#"<busconfig>
  <type>session</type>
  <listen>unix:tmpdir=/tmp</listen>
  <auth>EXTERNAL</auth>
  <policy context="default">
    <allow own="*"/>
    <allow send_destination="*"/>
    <allow receive_sender="*"/>
  </policy>
</busconfig>"#,
        )
        .unwrap();
        let result = Command::new("dbus-run-session")
            .arg("--config-file")
            .arg(config)
            .args(["--"])
            .arg(std::env::current_exe().unwrap())
            .args([
                "--exact",
                "the_command_forwards_links_to_the_existing_instance_on_a_private_bus",
                "--nocapture",
            ])
            .env(CHILD, "1")
            // The running copy's slot lives in the runtime directory, so a
            // Spotifast already running on this machine is left alone.
            .env("XDG_RUNTIME_DIR", &scratch.0)
            .output()
            .expect("the Linux test environment needs dbus-run-session");
        assert!(
            result.status.success(),
            "{}",
            String::from_utf8_lossy(&result.stderr)
        );
        return;
    }

    let scratch = Scratch::new();
    let result = Command::new(COMMAND).arg("reload-themes").output().unwrap();
    assert_eq!(result.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&result.stderr).contains("not running"));
    let result = Command::new(COMMAND).arg("like").output().unwrap();
    assert_eq!(result.status.code(), Some(1));
    assert!(
        String::from_utf8_lossy(&result.stderr).contains("not running"),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    let Outcome::Only(guard) = spotifast::single_instance::acquire(&Default::default(), None)
    else {
        panic!("the private bus must start without another instance");
    };
    let commands = guard.commands();
    for (link, uri) in [
        (
            "spotify:track:4uLU6hMCjMI75M1A2tKUQC",
            "spotify:track:4uLU6hMCjMI75M1A2tKUQC",
        ),
        (
            "https://open.spotify.com/search/here%20comes%20the%20sun",
            "spotify:search:here%20comes%20the%20sun",
        ),
        (
            "spotify://search/%E6%9D%B1%E4%BA%AC",
            "spotify:search:%E6%9D%B1%E4%BA%AC",
        ),
    ] {
        let mut child = Command::new(COMMAND)
            .arg(link)
            .env("XDG_CONFIG_HOME", scratch.0.join("config"))
            .env("XDG_STATE_HOME", scratch.0.join("state"))
            .env("XDG_CACHE_HOME", scratch.0.join("cache"))
            .spawn()
            .unwrap();
        let started = std::time::Instant::now();
        let status = loop {
            if let Some(status) = child.try_wait().unwrap() {
                break status;
            }
            if started.elapsed() > std::time::Duration::from_secs(10) {
                let _ = child.kill();
                let _ = child.wait();
                panic!("a second command did not forward its link and exit");
            }
            std::thread::sleep(std::time::Duration::from_millis(20));
        };
        assert!(status.success());
        assert_eq!(
            std::mem::take(&mut *commands.lock().unwrap()),
            vec![ControlCommand::OpenLink(uri.into())]
        );
    }
    let result = Command::new(COMMAND).arg("reload-themes").output().unwrap();
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    assert_eq!(
        std::mem::take(&mut *commands.lock().unwrap()),
        vec![ControlCommand::ReloadThemes],
        "a reload only asks for themes, never OpenLink or Show"
    );
    let result = Command::new(COMMAND).arg("like").output().unwrap();
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    assert_eq!(
        std::mem::take(&mut *commands.lock().unwrap()),
        vec![ControlCommand::ToggleSaved],
        "like only toggles the saved state, never OpenLink or Show"
    );
}
