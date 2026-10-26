// Copyright Unwritten Dao. All Rights Reserved.
// scaffold: UDialogueWidget is the C++ base for the in-game dialogue panel. The UMG
// hierarchy and bindings are created in the editor. It posts text to /v1/dialogue and
// displays the reply; proposals returned by the server are never applied client-side.

#pragma once

#include "Blueprint/UserWidget.h"
#include "CoreMinimal.h"
#include "Interfaces/IHttpRequest.h"
#include "Interfaces/IHttpResponse.h"
#include "DialogueWidget.generated.h"

DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FOnDialogueReply, const FString&, ReplyText);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FOnDialogueFailed, const FString&, ErrorMessage);

UCLASS(Abstract, BlueprintType)
class UNWRITTENDAO_API UDialogueWidget : public UUserWidget
{
	GENERATED_BODY()

public:
	virtual void NativeConstruct() override;
	virtual void NativeDestruct() override;

	/** Must be called before submitting; typically set when the player interacts with an NPC. */
	UFUNCTION(BlueprintCallable, Category = "World|Dialogue")
	void SetDialogueTarget(const FString& InNpcId, const FString& InPlayerId);

	/**
	 * Send one bounded player message. Returns false for locally invalid input or when a
	 * request is already in flight. Server text is authoritative for the reply.
	 */
	UFUNCTION(BlueprintCallable, Category = "World|Dialogue")
	bool SubmitDialogue(const FString& Message);

	UFUNCTION(BlueprintPure, Category = "World|Dialogue")
	bool IsAwaitingReply() const { return bAwaitingReply; }

	/** Blueprint hooks: update the editable text boxes and transcript here. */
	UFUNCTION(BlueprintImplementableEvent, Category = "World|Dialogue")
	void BP_OnReply(const FString& ReplyText);

	UFUNCTION(BlueprintImplementableEvent, Category = "World|Dialogue")
	void BP_OnError(const FString& ErrorMessage);

	UPROPERTY(BlueprintAssignable, Category = "World|Dialogue")
	FOnDialogueReply OnDialogueReply;

	UPROPERTY(BlueprintAssignable, Category = "World|Dialogue")
	FOnDialogueFailed OnDialogueFailed;

	UPROPERTY(BlueprintReadOnly, Category = "World|Dialogue")
	FString NpcId;

	UPROPERTY(BlueprintReadOnly, Category = "World|Dialogue")
	FString PlayerId;

	UPROPERTY(BlueprintReadOnly, Category = "World|Dialogue")
	FString LastReplyText;

	/** Raw JSON of the last response proposal, kept for debugging only; never executed. */
	UPROPERTY(BlueprintReadOnly, Category = "World|Dialogue")
	FString LastProposalJson;

protected:
	void HandleDialogueResponse(FHttpRequestPtr Request, FHttpResponsePtr Response, bool bConnected);
	void FinishWithError(int32 HttpStatus, const FString& Message);

private:
	bool bAwaitingReply = false;
};