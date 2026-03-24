document.addEventListener('DOMContentLoaded', () => {
    // Плавное появление карточек
    const cards = document.querySelectorAll('.book-card');
    cards.forEach((card, index) => {
        card.style.animationDelay = `${index * 0.05}s`;
    });

    // Модальное окно выдачи (как и ранее)
    const issueModal = document.getElementById('issueModal');
    if (issueModal) {
        issueModal.addEventListener('show.bs.modal', async (event) => {
            const button = event.relatedTarget;
            const bookId = button.getAttribute('data-book-id');
            const bookTitle = button.getAttribute('data-book-title');
            document.getElementById('book_title').textContent = bookTitle;
            const copyInput = document.getElementById('copy_id');
            try {
                const response = await fetch(`/api/available_copies?book_id=${bookId}`);
                const data = await response.json();
                if (data && data.length > 0) {
                    copyInput.value = data[0].copy_id;
                } else {
                    alert('Нет доступных экземпляров');
                    bootstrap.Modal.getInstance(issueModal).hide();
                }
            } catch (error) {
                console.error('Ошибка загрузки экземпляров:', error);
            }
        });
    }

    // Автоскрытие flash-сообщений
    setTimeout(() => {
        document.querySelectorAll('.alert').forEach(alert => {
            const bsAlert = new bootstrap.Alert(alert);
            bsAlert.close();
        });
    }, 5000);
});