# User Journeys

The rebuilt application supports a broad set of journeys. The list is deliberately larger than the visible navigation because several journeys share the same engine.

## Guest and first-use journeys

1. Open the application and use deterministic translation without an account.
2. Encode English text into strict and display ESHB.
3. Decode strict ESHB back to its normalized spelling.
4. Encode Swahili including digraphs such as SH, CH, NY, NG and NG'.
5. Encode IPA into reversible ESHB and decode it again.
6. Search a word in English, Swahili or Egyptological transliteration.
7. Browse the uniliteral sign table.
8. Convert MdC special consonants to Unicode Egyptological transliteration.
9. Render a known Egyptian lexeme using a stored teaching spelling.
10. See an explicitly labelled uniliteral fallback for an unknown historical spelling.
11. Begin a lesson and answer a knowledge check.
12. Keep guest lesson completion locally on the device.
13. Type English or Swahili and receive candidate-based historical analysis.
14. Supply context and intended meaning to improve interpretation.
15. Submit anonymous translation feedback.
16. Ask the browser to read ordinary English/Swahili text aloud.
17. Inspect the device capability report before granting permissions.

## Live multimodal journeys

18. Start rear-facing camera preview on a phone or tablet.
19. Take one inscription frame for analysis.
20. Enable automatic repeated frame analysis while holding the camera over an object.
21. Stop auto-scan without stopping the camera.
22. Stop camera access and release all tracks.
23. Enter archaeological/museum context for the image before analysis.
24. Speak English and translate the recognized transcript.
25. Speak Swahili and translate the recognized transcript.
26. Edit the transcript before translation when speech recognition mishears a word.
27. Read the best translation aloud.
28. Read an Egyptian transliteration aloud using an explicitly conventional classroom pronunciation.
29. Continue using typed speech input on browsers with no speech-recognition API.
30. Receive an honest provider-not-configured result instead of a fake camera translation.

## Learner journeys

31. Register a learner account.
32. Sign in and synchronize lesson progress.
33. View personal translation history.
34. Use configured cloud vision while authenticated.
35. Compare literal and natural readings when the engine or AI returns both.
36. Inspect confidence and provenance before accepting a translation.
37. Review ambiguity when one Egyptian form has several possible senses.
38. Learn suffix-pronoun analysis such as `rn.j`.
39. Use classroom pronunciation for study while seeing the historical-vowel disclaimer.
40. Install the PWA and reopen it from the home screen/app launcher.
41. Reopen the cached app shell while offline and use local/static learning features.

## Contributor journeys

42. Receive contributor permission from an administrator.
43. Propose a new transliteration with English and Swahili glosses.
44. Attach hieroglyphs, Gardiner codes and evidence notes.
45. Submit the proposal without changing the public/reviewed lexicon immediately.

## Reviewer journeys

46. Open the pending proposal queue.
47. Distinguish human-submitted and AI-generated proposals.
48. Approve a well-supported proposal and immediately make it searchable as a reviewed community entry.
49. Reject a weak or invented proposal.
50. Inspect recurring unresolved terms from real user translation attempts.
51. Inspect feedback counts.
52. Run AI research suggestions for repeated unknown terms.
53. Keep every AI suggestion pending until reviewed.

## Administrator journeys

54. Bootstrap the first administrator via environment secrets.
55. View users and their roles through the API.
56. Promote a learner to contributor, reviewer or administrator.
57. Disable a compromised or abusive account and invalidate its sessions.
58. Inspect audit events for role, review, feedback and learning-loop actions.
59. Configure external text AI without changing application code.
60. Configure external vision AI without changing application code.
61. Enable a scheduled daily research loop.
62. Deploy the same application in Docker on desktop/server infrastructure.

## Research and institutional journeys enabled by the architecture

63. Museum kiosk mode with camera and guided interpretation.
64. Archaeological field tablet mode with object-context notes.
65. University classroom mode with lesson progression and reviewed lexicon.
66. Epigrapher workflow comparing several transliteration candidates.
67. Curator workflow preserving provenance and confidence rather than one opaque translation.
68. Swahili-first heritage education for East African learners.
69. Accessibility workflow using speech input and read-aloud.
70. Collaborative vocabulary expansion with reviewer governance.
