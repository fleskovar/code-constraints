<script lang="ts">
  // Renders the editor's modal dialogs. Lives at the App.svelte level, OUTSIDE
  // the EditorPage/EditorCanvas subtree, because anywhere SvelteFlow is rendered
  // in a component's tree it disrupts that component's $state reactivity for
  // unrelated bindings. Keeping the modals at the App root sidesteps that.

  import type { AssociationDraft, ClassDraft } from "../../lib/api";
  import {
    addAssociation,
    addClass,
    closeAssocModal,
    closeClassModal,
    closeEdgePicker,
    defaultAssociation,
    editorState,
    findClass,
    iterClasses,
    modalState,
    openAssocModal,
    openClassModal,
    removeAssociation,
    removeClass,
    setBases,
    updateAssociation,
    updateClass,
  } from "../../lib/state/editor.svelte";

  import ClassEditModal from "./ClassEditModal.svelte";
  import AssociationEditModal from "./AssociationEditModal.svelte";
  import EdgeKindPickerModal from "./EdgeKindPickerModal.svelte";

  const classQnames = $derived(
    Array.from(iterClasses(editorState.project)).map((c) => c.qualified_name),
  );

  function saveClassModal(next: ClassDraft) {
    if (modalState.classExisting && modalState.classOriginalQname) {
      updateClass(modalState.classOriginalQname, next);
    } else {
      addClass(next);
    }
    closeClassModal();
  }

  function deleteFromClassModal() {
    if (!modalState.classExisting || !modalState.classOriginalQname) return;
    removeClass(modalState.classOriginalQname);
    closeClassModal();
  }

  function saveAssoc(next: AssociationDraft) {
    updateAssociation(modalState.assocIndex, next);
    closeAssocModal();
  }
  function deleteAssoc() {
    removeAssociation(modalState.assocIndex);
    closeAssocModal();
  }

  function pickEdgeKind(kind: "inheritance" | "association") {
    const sourceQname = modalState.edgePickerSourceLabel;
    const targetQname = modalState.edgePickerTargetLabel;
    if (!sourceQname || !targetQname) {
      closeEdgePicker();
      return;
    }
    if (kind === "inheritance") {
      const cls = findClass(sourceQname);
      if (cls && !cls.bases.includes(targetQname)) {
        setBases(sourceQname, [...cls.bases, targetQname]);
      }
      closeEdgePicker();
    } else {
      const assoc = defaultAssociation(sourceQname, targetQname);
      const newIndex = editorState.project.associations.length;
      addAssociation(assoc);
      closeEdgePicker();
      openAssocModal(assoc, newIndex, true);
    }
  }
</script>

{#if modalState.classOpen && modalState.classInitial}
  <ClassEditModal
    open
    initial={modalState.classInitial}
    isExisting={modalState.classExisting}
    onsave={saveClassModal}
    ondelete={modalState.classExisting ? deleteFromClassModal : undefined}
    onclose={closeClassModal}
  />
{/if}

{#if modalState.assocOpen && modalState.assocInitial}
  <AssociationEditModal
    open
    initial={modalState.assocInitial}
    {classQnames}
    isExisting={modalState.assocExisting}
    onsave={saveAssoc}
    ondelete={modalState.assocExisting ? deleteAssoc : undefined}
    onclose={closeAssocModal}
  />
{/if}

{#if modalState.edgePickerOpen}
  <EdgeKindPickerModal
    open
    sourceLabel={modalState.edgePickerSourceLabel}
    targetLabel={modalState.edgePickerTargetLabel}
    onpick={pickEdgeKind}
    onclose={closeEdgePicker}
  />
{/if}
