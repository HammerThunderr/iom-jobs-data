// Firebase accounts and event submissions (same project and rules as the app).
import { initializeApp, getApps } from 'firebase/app';
import {
  getAuth, onAuthStateChanged, signInWithEmailAndPassword, createUserWithEmailAndPassword,
  sendEmailVerification, sendPasswordResetEmail, signOut, reload, type User,
} from 'firebase/auth';
import {
  getFirestore, collection, addDoc, serverTimestamp, query, where, getDocs, deleteDoc, doc,
  writeBatch, updateDoc,
} from 'firebase/firestore';
import { FIREBASE } from './community';
import { esc, ic } from './client';

export const ADMIN_EMAILS = ['hammerpunch786@gmail.com'];

const app = getApps()[0] ?? initializeApp(FIREBASE);
export const auth = getAuth(app);
export const db = getFirestore(app);

export type Submission = Record<string, any> & { id: string };

export function isAdmin(u: User | null) {
  return !!u && u.emailVerified && ADMIN_EMAILS.includes((u.email || '').toLowerCase());
}

export function friendlyError(e: any): string {
  const c = String(e?.code || e?.message || '');
  if (/invalid-credential|wrong-password|user-not-found/.test(c)) return 'Email or password is incorrect.';
  if (/email-already-in-use/.test(c)) return 'That email already has an account. Sign in instead.';
  if (/weak-password/.test(c)) return 'Choose a password of at least 6 characters.';
  if (/invalid-email/.test(c)) return 'That email address doesn’t look right.';
  if (/too-many-requests/.test(c)) return 'Too many attempts. Please wait a few minutes.';
  if (/network/.test(c)) return 'No connection. Check your internet and try again.';
  if (/permission-denied/.test(c)) return 'That wasn’t allowed. Check every field and that your email is verified.';
  if (/unauthorized-domain/.test(c)) return 'Sign-in isn’t enabled for this website address yet.';
  return 'Something went wrong. Please try again.';
}

/**
 * Renders a sign-in panel into `box` until the person is signed in with a
 * verified email, then calls `ready(user)`.
 */
export function requireVerifiedUser(box: HTMLElement, ready: (u: User) => void, signedOut?: () => void) {
  let mode: 'in' | 'up' = 'in';
  const paintSignIn = (msg = '') => {
    box.innerHTML = `<div class="card pad-lg auth">
      <h2>${mode === 'in' ? 'Sign in' : 'Create an account'}</h2>
      <p class="muted small">An account lets you add events and see whether they've been approved. It's the same account as the Manx One app.</p>
      <form id="auth-form" class="stack">
        <label class="field"><span>Email</span><input class="input" type="email" name="email" autocomplete="email" required></label>
        <label class="field"><span>Password</span><input class="input" type="password" name="password" minlength="6" autocomplete="${mode === 'in' ? 'current-password' : 'new-password'}" required></label>
        ${msg ? `<p class="notice bad">${ic('error')}<span>${esc(msg)}</span></p>` : ''}
        <div class="btn-row"><button class="btn" type="submit">${mode === 'in' ? 'Sign in' : 'Create account'}</button>
        <button class="btn ghost sm" type="button" id="auth-switch">${mode === 'in' ? 'New here? Create an account' : 'Have an account? Sign in'}</button></div>
        ${mode === 'in' ? '<button class="linkish small" type="button" id="auth-reset">Forgotten your password?</button>' : ''}
      </form></div>`;
    const form = box.querySelector('#auth-form') as HTMLFormElement;
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const fd = new FormData(form);
      const email = String(fd.get('email')).trim();
      const pw = String(fd.get('password'));
      (form.querySelector('button[type=submit]') as HTMLButtonElement).disabled = true;
      try {
        if (mode === 'in') await signInWithEmailAndPassword(auth, email, pw);
        else {
          const cred = await createUserWithEmailAndPassword(auth, email, pw);
          await sendEmailVerification(cred.user);
        }
      } catch (err) {
        paintSignIn(friendlyError(err));
      }
    });
    box.querySelector('#auth-switch')!.addEventListener('click', () => {
      mode = mode === 'in' ? 'up' : 'in';
      paintSignIn();
    });
    box.querySelector('#auth-reset')?.addEventListener('click', async () => {
      const email = (form.querySelector('input[name=email]') as HTMLInputElement).value.trim();
      if (!email) return paintSignIn('Type your email first, then press “Forgotten your password?”.');
      try {
        await sendPasswordResetEmail(auth, email);
        paintSignIn('If that email has an account, a reset link is on its way.');
      } catch (err) {
        paintSignIn(friendlyError(err));
      }
    });
  };
  const paintVerify = (u: User, msg = '') => {
    box.innerHTML = `<div class="card pad-lg">
      <h2>Check your email</h2>
      <p>We sent a link to <strong>${esc(u.email)}</strong>. Open it to confirm your address, then come back and press the button below.</p>
      ${msg ? `<p class="notice">${ic('info')}<span>${esc(msg)}</span></p>` : ''}
      <div class="btn-row"><button class="btn" id="v-done" type="button">I've confirmed my email</button>
      <button class="btn ghost sm" id="v-resend" type="button">Send the link again</button>
      <button class="btn ghost sm" id="v-out" type="button">Sign out</button></div></div>`;
    box.querySelector('#v-done')!.addEventListener('click', async () => {
      await reload(u);
      if (auth.currentUser?.emailVerified) {
        await auth.currentUser.getIdToken(true);
        box.innerHTML = '';
        ready(auth.currentUser);
      } else paintVerify(u, 'Not confirmed yet. Check your inbox and spam folder.');
    });
    box.querySelector('#v-resend')!.addEventListener('click', async () => {
      try {
        await sendEmailVerification(u);
        paintVerify(u, 'Sent. It can take a minute to arrive.');
      } catch (err) {
        paintVerify(u, friendlyError(err));
      }
    });
    box.querySelector('#v-out')!.addEventListener('click', () => signOut(auth));
  };
  onAuthStateChanged(auth, (u) => {
    if (!u) {
      paintSignIn();
      signedOut?.();
    } else if (!u.emailVerified) paintVerify(u);
    else {
      box.innerHTML = '';
      ready(u);
    }
  });
}

export function signOutNow() {
  return signOut(auth);
}

export async function submitEvent(u: User, f: Record<string, string>) {
  await addDoc(collection(db, 'event_submissions'), {
    uid: u.uid,
    submitterEmail: u.email || '',
    title: f.title.trim(),
    venue: f.venue.trim(),
    area: f.area,
    category: f.category,
    startDate: f.startDate,
    endDate: f.endDate || f.startDate,
    startTime: f.startTime || '',
    endTime: f.endTime || '',
    description: f.description.trim(),
    price: (f.price || '').trim(),
    url: (f.url || '').trim(),
    imageUrl: (f.imageUrl || '').trim(),
    organiser: f.organiser.trim(),
    contactEmail: f.contactEmail.trim(),
    status: 'pending',
    createdAt: serverTimestamp(),
  });
}

const sortNewest = (a: Submission, b: Submission) => (b.createdAt?.seconds ?? 0) - (a.createdAt?.seconds ?? 0);

export async function mySubmissions(u: User): Promise<Submission[]> {
  const snap = await getDocs(query(collection(db, 'event_submissions'), where('uid', '==', u.uid)));
  return snap.docs.map((d) => ({ id: d.id, ...d.data() })).sort(sortNewest);
}

export async function withdraw(id: string) {
  await deleteDoc(doc(db, 'event_submissions', id));
}

export async function byStatus(status: string): Promise<Submission[]> {
  const snap = await getDocs(query(collection(db, 'event_submissions'), where('status', '==', status)));
  const list = snap.docs.map((d) => ({ id: d.id, ...d.data() }));
  return status === 'pending' ? list.sort((a, b) => -sortNewest(a, b)) : list.sort(sortNewest);
}

export async function approve(s: Submission) {
  const b = writeBatch(db);
  b.set(doc(db, 'community_events', s.id), {
    title: s.title, venue: s.venue, area: s.area, category: s.category,
    startDate: s.startDate, endDate: s.endDate || s.startDate, startTime: s.startTime || '', endTime: s.endTime || '',
    description: s.description, price: s.price || '', url: s.url || '', imageUrl: s.imageUrl || '', organiser: s.organiser,
    submissionId: s.id, approvedAt: serverTimestamp(),
  });
  b.update(doc(db, 'event_submissions', s.id), { status: 'approved', reviewedAt: serverTimestamp(), reviewNote: '' });
  await b.commit();
}

export async function reject(s: Submission, reason: string) {
  await updateDoc(doc(db, 'event_submissions', s.id), { status: 'rejected', reviewedAt: serverTimestamp(), reviewNote: reason.trim() });
}

export async function unpublish(s: Submission) {
  const b = writeBatch(db);
  b.delete(doc(db, 'community_events', s.id));
  b.update(doc(db, 'event_submissions', s.id), { status: 'removed', reviewedAt: serverTimestamp() });
  await b.commit();
}

/*icons*/ ['error', 'info'];
