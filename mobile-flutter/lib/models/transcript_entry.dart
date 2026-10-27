/// A single turn in the shared voice+text conversation.
class TranscriptEntry {
  const TranscriptEntry({
    required this.id,
    required this.role,
    required this.text,
    required this.isVoice,
  });

  final String id;
  final String role; // 'user' | 'agent'
  final String text;
  final bool isVoice;

  TranscriptEntry.fromInput(this.id, this.text, {required this.isVoice}) : role = 'user';

  /// Survives process death (see SessionPersistence).
  factory TranscriptEntry.fromJson(Map<String, dynamic> json) => TranscriptEntry(
        id: (json['id'] ?? '') as String,
        role: (json['role'] ?? 'agent') as String,
        text: (json['text'] ?? '') as String,
        isVoice: json['isVoice'] == true,
      );

  Map<String, dynamic> toJson() => {
        'id': id,
        'role': role,
        'text': text,
        'isVoice': isVoice,
      };
}
