STEP_LABELS = [
    "NAVIGATION_OR_ACCESS",
    "LIST_OR_SEARCH",
    "DETAIL_VIEW",
    "CREATE_OR_REGISTER",
    "FORM_INPUT",
    "UPDATE_OR_EDIT",
    "SUBMIT_OR_SAVE",
    "APPROVAL_OR_CONFIRM",
    "UPLOAD_OR_DOWNLOAD",
    "ERROR_OR_EXCEPTION",
    "IDLE_OR_NOISE",
]

STEP_LABEL_TO_ID = {label: index for index, label in enumerate(STEP_LABELS)}
ID_TO_STEP_LABEL = {index: label for label, index in STEP_LABEL_TO_ID.items()}
