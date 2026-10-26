// Copyright Unwritten Dao. All Rights Reserved.

#include "DialogueWidget.h"

#include "Dom/JsonObject.h"
#include "Dom/JsonValue.h"
#include "HttpModule.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"
#include "UnwrittenDao.h"
#include "WorldSyncSubsystem.h"

void UDialogueWidget::NativeConstruct()
{
	Super::NativeConstruct();

	if (PlayerId.IsEmpty())
	{
		if (UWorld* World = GetWorld())
		{
			if (UWorldSyncSubsystem* Sync = World->GetSubsystem<UWorldSyncSubsystem>())
			{
				PlayerId = Sync->GetPlayerId();
			}
		}
	}
}

void UDialogueWidget::NativeDestruct()
{
	// In-flight callbacks are cancelled when this object is collected; no local state to undo.
	Super::NativeDestruct();
}

void UDialogueWidget::SetDialogueTarget(const FString& InNpcId, const FString& InPlayerId)
{
	NpcId = InNpcId;
	if (!InPlayerId.IsEmpty())
	{
		PlayerId = InPlayerId;
	}
}

bool UDialogueWidget::SubmitDialogue(const FString& Message)
{
	const FString Trimmed = Message.TrimStartAndEnd();
	if (NpcId.IsEmpty())
	{
		FinishWithError(0, TEXT("No NPC selected for dialogue."));
		return false;
	}
	if (Trimmed.IsEmpty() || Trimmed.Len() > 2000)
	{
		FinishWithError(0, TEXT("Message must contain 1-2000 characters."));
		return false;
	}
	if (bAwaitingReply)
	{
		FinishWithError(0, TEXT("Waiting for the previous reply."));
		return false;
	}

	UWorld* World = GetWorld();
	UWorldSyncSubsystem* Sync = World ? World->GetSubsystem<UWorldSyncSubsystem>() : nullptr;
	if (!Sync)
	{
		FinishWithError(0, TEXT("World sync subsystem is unavailable."));
		return false;
	}
	if (PlayerId.IsEmpty())
	{
		PlayerId = Sync->GetPlayerId();
	}
	if (PlayerId.IsEmpty())
	{
		FinishWithError(0, TEXT("No player_id is available from the snapshot."));
		return false;
	}

	TSharedPtr<FJsonObject> Body = MakeShared<FJsonObject>();
	Body->SetStringField(TEXT("npc_id"), NpcId);
	Body->SetStringField(TEXT("player_id"), PlayerId);
	Body->SetStringField(TEXT("message"), Trimmed);

	FString BodyText;
	const TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&BodyText);
	FJsonSerializer::Serialize(Body.ToSharedRef(), Writer);

	const TSharedRef<IHttpRequest, ESPMode::ThreadSafe> Request = FHttpModule::Get().CreateRequest();
	Request->SetURL(Sync->GetBaseUrl() + TEXT("/v1/dialogue"));
	Request->SetVerb(TEXT("POST"));
	Request->SetHeader(TEXT("Content-Type"), TEXT("application/json"));
	Request->SetHeader(TEXT("Accept"), TEXT("application/json"));
	Request->SetTimeout(20.0f);
	Request->SetContentAsString(BodyText);
	Request->OnProcessRequestComplete().BindUObject(
		this, &UDialogueWidget::HandleDialogueResponse);

	bAwaitingReply = true;
	if (!Request->ProcessRequest())
	{
		bAwaitingReply = false;
		FinishWithError(0, TEXT("Dialogue request could not be sent."));
		return false;
	}
	return true;
}

void UDialogueWidget::HandleDialogueResponse(
	FHttpRequestPtr Request, FHttpResponsePtr Response, bool bConnected)
{
	bAwaitingReply = false;

	if (!bConnected || !Response.IsValid())
	{
		FinishWithError(0, TEXT("World server did not respond."));
		return;
	}

	const int32 Status = Response->GetResponseCode();
	TSharedPtr<FJsonObject> Root;
	const TSharedRef<TJsonReader<>> Reader =
		TJsonReaderFactory<>::Create(Response->GetContentAsString());
	FJsonSerializer::Deserialize(Reader, Root);

	if (Status != EHttpResponseCodes::Ok || !Root.IsValid())
	{
		FString Message = TEXT("Dialogue request failed.");
		if (Root.IsValid())
		{
			Root->TryGetStringField(TEXT("message"), Message);
		}
		FinishWithError(Status, Message);
		return;
	}

	FString Reply;
	if (!Root->TryGetStringField(TEXT("reply_text"), Reply))
	{
		FinishWithError(Status, TEXT("Response did not contain reply_text."));
		return;
	}

	LastReplyText = Reply;
	LastProposalJson.Reset();

	// A proposal is informational only. The client never validates or applies it.
	const TSharedPtr<FJsonObject>* Proposal = nullptr;
	if (Root->TryGetObjectField(TEXT("proposal"), Proposal) && Proposal && Proposal->IsValid())
	{
		const TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&LastProposalJson);
		FJsonSerializer::Serialize(Proposal->ToSharedRef(), Writer);
		UE_LOG(LogUnwrittenDao, Verbose,
			TEXT("Dialogue: proposal stored for inspection; client does not apply it."));
	}

	OnDialogueReply.Broadcast(LastReplyText);
	BP_OnReply(LastReplyText);
}

void UDialogueWidget::FinishWithError(int32 HttpStatus, const FString& Message)
{
	UE_LOG(LogUnwrittenDao, Warning, TEXT("Dialogue: HTTP %d: %s"), HttpStatus, *Message);
	OnDialogueFailed.Broadcast(Message);
	BP_OnError(Message);
}