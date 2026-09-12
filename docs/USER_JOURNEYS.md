# User journeys

The platform is designed so that the same linguistic core supports learners, visitors, field researchers and reviewers without giving every role the same write permissions.

## Guest journeys

1. Open the site on a phone and translate an English word to a reviewed Middle Egyptian lemma.
2. Enter a Swahili word and see Egyptian, English and Swahili lexical relationships.
3. Translate a supported phrase and inspect its grammar template.
4. Add context to a phrase and receive alternative interpretations.
5. Disable AI review and use only deterministic dictionary/grammar output.
6. Open Live Lens, grant camera permission and capture an inscription.
7. Enable live sampled-frame scanning on a museum object.
8. Upload a high-quality archival scan from a desktop with no camera.
9. Ask the lens to explain candidates in Swahili.
10. Tap read-aloud and hear an English or Swahili explanation.
11. Open Talk, dictate an English phrase and translate it to Egyptian.
12. Dictate Swahili and receive a translated response.
13. Enable live conversation translation so each completed utterance is translated and optionally spoken immediately.
14. Hear conventional classroom pronunciation for an Egyptian transliteration.
15. Browse the trilingual dictionary.
16. Search by English, Swahili or transliteration.
17. Study a lesson and hear its transliterated example.
18. Answer lesson quiz questions locally as a guest.
19. Use the ESHB strict encoder and recover the original spelling.
20. Convert IPA to ESHB and back.
21. Convert common MdC special letters to Unicode transliteration.
22. Parse a line made only from known uniliteral signs.
23. Install the app as a PWA where the browser supports installation.
24. Reopen the cached application shell when temporarily offline.

## Learner journeys

25. Create an account and receive the learner role.
26. Sign in on a phone/tablet/desktop.
27. Complete a quiz and persist progress under the authenticated account.
28. Save a contextual translation to personal history when explicitly requested.
29. Review personal translation history.
30. Clear personal translation history.
31. Submit a helpful/not-helpful translation rating with an optional correction for reviewer inspection.
32. Sign out and return to guest behavior.

## Contributor journeys

33. Receive contributor role from an administrator.
34. Submit a proposed lexicon entry with English and Swahili glosses.
35. Attach bibliographic/object evidence and a source URL.
36. Mark a proposal's confidence without directly changing the live dictionary.
37. Continue using all learner features while a proposal is pending.

## Reviewer journeys

38. Open the pending knowledge queue.
39. Inspect an AI-generated draft and distinguish it from a human proposal.
40. Verify a proposed lemma against an external scholarly source.
41. Approve a proposal and make it available as a reviewed runtime lexicon overlay.
42. Reject an unsupported proposal with a review note.
43. Inspect repeated unresolved terms that users encounter.
44. Observe the knowledge-loop schedule/status.

## Admin journeys

45. Bootstrap an admin through server environment configuration.
46. View registered users.
47. Promote a learner to contributor.
48. Promote a contributor to reviewer.
49. Revoke a role by returning a user to learner.
50. Manually run an AI draft cycle for high-frequency unresolved terms.
51. Keep AI drafting disabled entirely while preserving deterministic translation.
52. Deploy with secure cookies behind HTTPS.

## Field / museum journeys

53. Use a phone rear camera against a wall inscription.
54. Switch to low-detail vision on limited mobile bandwidth.
55. Add context such as “funerary stela” before image analysis.
56. Compare several transliteration candidates instead of seeing one forced reading.
57. View possible Gardiner codes and sign values with confidence.
58. See uncertainty notices for damaged/obscured signs.
59. Read the translation aloud to a visitor.
60. Pause live scanning automatically when the app goes into the background.
61. Stop the camera and release device tracks immediately.
62. Switch between rear/environment and front/user-facing camera preferences on supported devices.

## Accessibility journeys

63. Navigate the interface entirely by keyboard.
64. Use visible focus states.
65. Use OS/browser dictation if built-in SpeechRecognition is unavailable.
66. Hear classroom readings instead of relying on visual glyph recognition.
67. Use reduced-motion OS preferences to suppress scan/pulse animations.
68. Use a screen reader with labelled controls and live status regions.

## Evidence and governance journeys

- A reviewer opens learner feedback and sees recurring corrections that may justify a knowledge proposal.
- A reviewer inspects an AI-generated lexicon draft, adds a real source URL, writes a review note and only then approves it.
- An AI-generated draft without reviewer-supplied source evidence is rejected by the server if approval is attempted.

## Research journeys enabled by the architecture but requiring future data layers

69. Compare attested spellings by historical period.
70. Rank damaged-sign restorations against a corpus.
71. Move from hieroglyphic to hieratic/demotic/Coptic evidence.
72. Export scholarly annotations in a structured epigraphic format.
73. Train/evaluate a dedicated sign-recognition model on reviewer-approved labels.
