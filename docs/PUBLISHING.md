# Publishing ClipStack

This guide takes you from this Git repository to:

```bash
sudo add-apt-repository ppa:MY_NAME/clipstack
sudo apt update
sudo apt install clipstack
```

Replace **`MY_NAME`** everywhere with your Launchpad username.

Overview:

1. Create a Launchpad account and a PPA
2. Create a GPG key and register it
3. Build a signed source package and upload it
4. Do one upload per Ubuntu release (22.04, 24.04, 26.04, …)
5. Release new versions later
6. Alternative: host your own APT repository on GitHub Pages

Launchpad builds the `.deb` files itself from your **source** package. You
never upload `.deb` files to a PPA.

---

## 1. Launchpad account and PPA

1. Go to <https://launchpad.net/> and click **Log in / Register**. Create an
   Ubuntu One account. Use the **same e-mail** you put in `debian/changelog`
   (the `-- Name <email>` line).
2. Open your profile (`https://launchpad.net/~MY_NAME`). Check your username:
   it appears in the URL and in `ppa:MY_NAME/...`.
3. If Launchpad asks you to sign the Ubuntu Code of Conduct, do it from your
   profile page.
4. On your profile page click **Create a new PPA**:
   - URL: `clipstack`
   - Display name: `ClipStack`
   - Description: `Win+V style clipboard history for Ubuntu`
   Click **Activate**.

Your PPA is now at `https://launchpad.net/~MY_NAME/+archive/ubuntu/clipstack`.

## 2. GPG key

Launchpad accepts only uploads signed with a GPG key that is registered on your
account.

### 2.1 Create the key

```bash
gpg --full-generate-key
```

Answer:

- Kind: **RSA and RSA** (or the default ECC (sign and encrypt) on a recent GnuPG)
- Size: **4096** (for RSA)
- Expiry: e.g. `2y` (you can extend it later)
- Real name and e-mail: **exactly** the same as in `debian/changelog`
- A passphrase you will remember

Show the key and copy the 40-character **fingerprint**:

```bash
gpg --list-secret-keys --keyid-format=long
# sec   rsa4096/ABCDEF0123456789 2026-11-19 [SC]
#       0123456789ABCDEF0123456789ABCDEF01234567   <- fingerprint
```

### 2.2 Upload it to the Ubuntu keyserver

```bash
gpg --keyserver keyserver.ubuntu.com --send-keys 0123456789ABCDEF0123456789ABCDEF01234567
```

Wait a few minutes. Check it is there by searching the fingerprint on
<https://keyserver.ubuntu.com/>.

### 2.3 Add it to Launchpad

1. Go to `https://launchpad.net/~MY_NAME/+editpgpkeys`.
2. Paste the fingerprint and click **Import Key**.
3. Launchpad sends you an **encrypted** e-mail. Save the encrypted text
   (from `-----BEGIN PGP MESSAGE-----` to `-----END PGP MESSAGE-----`) to a
   file and decrypt it:

   ```bash
   gpg --decrypt message.txt
   ```

4. Open the link in the decrypted text and click **Continue** to confirm.

### 2.4 Tell the Debian tools who you are

`setup.sh` already added these to `~/.bashrc`. Check them:

```bash
echo "$DEBFULLNAME <$DEBEMAIL>"     # must match the key's name and e-mail
```

Optional: pin the key that `debuild` uses for signing:

```bash
echo 'DEBSIGN_KEYID=0123456789ABCDEF0123456789ABCDEF01234567' >> ~/.devscripts
```

## 3. Build a signed source package and upload it

Start from a clean, committed tree. Untracked files would end up in the source
package (`CLAUDE_CODE_PROMPT.md` and `setup.sh` are already excluded by
`debian/source/options`).

```bash
cd ~/Workspace/clipStack       # the project folder
git status                     # should be clean
python3 -m unittest            # tests pass
```

Build the **source** package. `-S` means source only, and it is signed with
your key (you will be asked for the passphrase):

```bash
debuild -S
```

This creates these files in the parent folder:

```
../clipstack_1.0.0.dsc
../clipstack_1.0.0.tar.xz
../clipstack_1.0.0_source.changes
```

Upload the `.changes` file:

```bash
dput ppa:MY_NAME/clipstack ../clipstack_1.0.0_source.changes
```

Within a few minutes Launchpad e-mails you **Accepted** (or a rejection with
the reason). The build then shows up on your PPA page under **View package
details**. When it says **Successfully built** and **Published**, users can install it.

> `debian/changelog` currently targets one release (`resolute`, Ubuntu 26.04).
> To support more releases, use step 4 instead of uploading that version
> directly.

## 4. Support Ubuntu 22.04, 24.04 and newer

Each upload targets **one** Ubuntu release, written in the first line of
`debian/changelog`:

```
clipstack (1.0.0) resolute; urgency=medium
```

| Ubuntu | Codename |
|---|---|
| 22.04 LTS | `jammy` |
| 24.04 LTS | `noble` |
| 26.04 LTS | `resolute` |
| newer | see <https://wiki.ubuntu.com/Releases> |

A PPA never accepts the same version twice, even for different releases, so
each release gets its own version suffix. Using `+ubuntuXX.YY.1` keeps the
versions in the right order: a newer Ubuntu gets a higher version, and all of
them are higher than a plain `1.0.0` built locally.

Run this loop from the project folder. It adds a temporary changelog entry per
release, builds, uploads, and restores the changelog:

```bash
VERSION=1.0.0
for rel in jammy:22.04 noble:24.04 resolute:26.04; do
  code=${rel%%:*}; num=${rel##*:}
  cp debian/changelog /tmp/clipstack-changelog.bak
  dch -v "${VERSION}+ubuntu${num}.1" -D "$code" --force-distribution \
      "Build for Ubuntu ${num}."
  debuild -S
  dput ppa:MY_NAME/clipstack "../clipstack_${VERSION}+ubuntu${num}.1_source.changes"
  cp /tmp/clipstack-changelog.bak debian/changelog
done
```

Notes:

- ClipStack is architecture `all` and pure Python (3.10 or newer), so the same
  source builds on every release from 22.04 on.
- If a build fails on one release, fix it, bump that release's suffix
  (`.1` to `.2`) and upload again. Launchpad never reuses a version.
- Instead of uploading again, you can also **copy** a package to another
  release on the PPA page (*View package details → Copy packages*). This only works when
  the binary also runs there, which is true for ClipStack.

## 5. Release a new version later

1. Make and commit your changes. Run the tests.
2. Update the version in `clipstack/__init__.py` (`__version__ = "1.0.1"`).
3. Add a changelog entry. `dch -i` opens an editor with a new entry. Change the
   version to `1.0.1` and describe the changes:

   ```bash
   dch -i
   # clipstack (1.0.1) resolute; urgency=medium
   #
   #   * Fix ...
   #
   #  -- Your Name <you@example.com>  Mon, 01 Feb 2027 10:00:00 +0000
   ```

   (Or in one line: `dch -v 1.0.1 -D resolute "Fix ..."`.)
4. Commit and tag:

   ```bash
   git commit -am "Release 1.0.1" && git tag v1.0.1
   ```

5. Build and upload for every release with the loop from step 4, using
   `VERSION=1.0.1`.

Users get the update with:

```bash
sudo apt update && sudo apt upgrade
```

## 6. Alternative: your own APT repository on GitHub Pages (free)

If you don't want to use Launchpad, you can host a signed APT repository as a
static website. You upload the `.deb` you built yourself (`debuild -us -uc -b`),
and the same `.deb` works on Ubuntu 22.04 and newer.

### 6.1 Create the repository files

```bash
KEY=0123456789ABCDEF0123456789ABCDEF01234567     # your GPG fingerprint
mkdir -p ~/clipstack-apt && cd ~/clipstack-apt
cp ~/Workspace/clipstack_1.0.0_all.deb .

dpkg-scanpackages --multiversion . /dev/null > Packages
gzip -k -f Packages
apt-ftparchive release . > Release
gpg --default-key "$KEY" -abs -o Release.gpg Release
gpg --default-key "$KEY" --clearsign -o InRelease Release
gpg --armor --export "$KEY" > clipstack.asc
touch .nojekyll        # let GitHub Pages serve every file as-is
```

`dpkg-scanpackages` comes with `dpkg-dev` and `apt-ftparchive` with
`apt-utils`. Both are already installed with the packaging tools.

### 6.2 Publish it

1. Create a **public** GitHub repository, e.g. `clipstack-apt`.
2. Push the folder:

   ```bash
   git init -b main && git add . && git commit -m "ClipStack 1.0.0"
   git remote add origin git@github.com:MY_NAME/clipstack-apt.git
   git push -u origin main
   ```

3. On GitHub: **Settings → Pages → Build and deployment → Deploy from a
   branch → `main` / `(root)`** → Save. After a minute the site is live at
   `https://MY_NAME.github.io/clipstack-apt/`.

### 6.3 What users run

```bash
sudo install -d -m 0755 /etc/apt/keyrings
curl -fsSL https://MY_NAME.github.io/clipstack-apt/clipstack.asc \
  | sudo tee /etc/apt/keyrings/clipstack.asc > /dev/null
echo "deb [signed-by=/etc/apt/keyrings/clipstack.asc] https://MY_NAME.github.io/clipstack-apt ./" \
  | sudo tee /etc/apt/sources.list.d/clipstack.list
sudo apt update
sudo apt install clipstack
```

### 6.4 New versions

Copy the new `.deb` into `~/clipstack-apt`, run the commands from 6.1 again
(all except `gpg --export`), then commit and push. Users get it with
`sudo apt update && sudo apt upgrade`.

---

## Checklist before every upload

- [ ] `python3 -m unittest` passes
- [ ] `debuild -us -uc -b` builds and `lintian ../clipstack_*_all.deb` shows no errors
- [ ] Installed the `.deb` locally and checked Super + B, paste, pin, delete
- [ ] `__version__` and `debian/changelog` show the same version
- [ ] Changelog signature line matches your GPG key's name and e-mail
