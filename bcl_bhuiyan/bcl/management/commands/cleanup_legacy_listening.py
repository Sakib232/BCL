import os
from django.core.management.base import BaseCommand
from django.db import transaction
from bcl.models import IELTSMockTest, ExamModule, ExamSection, Question, CandidateAnswer, CandidateAttempt


class Command(BaseCommand):
    help = (
        "Clean up legacy non-HTML Listening module data (audio files, database sections, "
        "and questions) for Mock Tests 1, 2, 3, and 4 while keeping all HTML files, "
        "static audio, and Reading/Writing modules completely untouched."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--test-numbers",
            nargs="+",
            type=int,
            default=[1, 2, 3, 4],
            help="Mock test numbers to clean up (default: 1 2 3 4).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be deleted without modifying the database or disk.",
        )
        parser.add_argument(
            "--delete-audio-files",
            action="store_true",
            help="Also delete the legacy media MP3 files from disk (in media/ielts/audio/).",
        )
        parser.add_argument(
            "--include-attempts",
            action="store_true",
            help="Also delete past candidate attempts for these legacy listening modules.",
        )

    def handle(self, *args, **options):
        test_numbers = options["test_numbers"]
        dry_run = options["dry_run"]
        delete_audio = options["delete_audio_files"]
        include_attempts = options["include_attempts"]

        self.stdout.write(
            self.style.NOTICE(
                f"=== Legacy Listening Cleanup (Mock Tests: {test_numbers}) ==="
            )
        )
        if dry_run:
            self.stdout.write(self.style.WARNING("[DRY RUN MODE - No changes will be applied]"))

        mocks = IELTSMockTest.objects.filter(test_number__in=test_numbers)
        if not mocks.exists():
            self.stdout.write(self.style.WARNING("No mock tests found matching test numbers."))
            return

        listening_modules = ExamModule.objects.filter(
            mock_test__in=mocks,
            module_type=ExamModule.ModuleType.LISTENING,
        )

        sections = ExamSection.objects.filter(module__in=listening_modules)
        questions = Question.objects.filter(section__in=sections)
        attempts = CandidateAttempt.objects.filter(module__in=listening_modules)

        audio_files_to_delete = []
        for mod in listening_modules:
            if mod.audio_file:
                audio_files_to_delete.append((mod, mod.audio_file.path, mod.audio_file.name))

        self.stdout.write(f"Listening modules found: {listening_modules.count()}")
        self.stdout.write(f"Legacy questions to delete: {questions.count()}")
        self.stdout.write(f"Legacy sections to delete: {sections.count()}")
        self.stdout.write(f"Legacy audio file references: {len(audio_files_to_delete)}")
        if include_attempts:
            self.stdout.write(f"Candidate attempts to delete: {attempts.count()}")
        else:
            self.stdout.write(f"Candidate attempts preserved ({attempts.count()} records). Use --include-attempts to purge.")

        if dry_run:
            self.stdout.write(self.style.SUCCESS("Dry run completed successfully. No changes made."))
            return

        with transaction.atomic():
            q_count = questions.count()
            s_count = sections.count()

            # 1. Delete protected answers pointing to these questions
            CandidateAnswer.objects.filter(question__in=questions).delete()

            # 2. Delete questions and sections
            questions.delete()
            sections.delete()

            # 2. Optionally delete attempts
            att_count = 0
            if include_attempts:
                att_count = attempts.count()
                attempts.delete()

            # 3. Clear audio_file field on modules
            for mod, file_path, file_name in audio_files_to_delete:
                mod.audio_file = ""
                mod.save(update_fields=["audio_file"])

        # 4. Physically remove audio files from disk if requested
        files_deleted_count = 0
        if delete_audio:
            for mod, file_path, file_name in audio_files_to_delete:
                if os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                        files_deleted_count += 1
                        self.stdout.write(f"Deleted file: {file_path}")
                    except OSError as e:
                        self.stdout.write(self.style.WARNING(f"Could not delete {file_path}: {e}"))

        self.stdout.write(
            self.style.SUCCESS(
                f"\nCleanup complete:\n"
                f"- {q_count} legacy questions removed\n"
                f"- {s_count} legacy sections removed\n"
                f"- {len(audio_files_to_delete)} audio references cleared from ExamModule\n"
                f"- {files_deleted_count} files removed from disk\n"
                f"- {att_count} candidate attempts removed\n"
                f"- HTML files and static audio remain 100% intact!"
            )
        )

